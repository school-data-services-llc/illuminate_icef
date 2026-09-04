import logging
import os

from google.cloud import bigquery

PROJECT_ID = "icef-437920"
AUDIT_TABLE = f"{PROJECT_ID}.logging.data_pipeline_audit"
GUARDED_TABLES = {
    "assessment_results_group",
    "assessment_results_combined",
    "illuminate_assessment_results",
}


def _allow_row_shrink():
    return os.getenv("ALLOW_ROW_SHRINK", "").strip().lower() in {"1", "true", "yes"}


def get_previous_upload_row_count(client, table_name, dag_name):
    query = f"""
    SELECT current_rows_added
    FROM `{AUDIT_TABLE}`
    WHERE table_name = @table_name
      AND dag_name = @dag_name
    ORDER BY run_date DESC
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("table_name", "STRING", table_name),
            bigquery.ScalarQueryParameter("dag_name", "STRING", dag_name),
        ]
    )
    result = client.query(query, job_config=job_config).result()
    row = next(result, None)
    return row.current_rows_added if row else None


def validate_upload_row_count(frame, table_name, dag_name, client):
    """Refuse upload if this run has fewer rows than the last successful audit row."""
    current_rows = 0 if frame is None else len(frame)
    previous_rows = get_previous_upload_row_count(client, table_name, dag_name)

    if previous_rows is None:
        logging.info(f"No prior audit row for {table_name}; skipping row-count guard")
        return

    if current_rows < previous_rows:
        message = (
            f"Refusing to upload {table_name}.csv: current row count {current_rows} "
            f"is below previous row count {previous_rows} (diff {current_rows - previous_rows})."
        )
        if _allow_row_shrink():
            logging.warning(f"{message} ALLOW_ROW_SHRINK is set; continuing.")
            return
        raise RuntimeError(message)

    logging.info(
        f"Row-count guard passed for {table_name}: current={current_rows}, previous={previous_rows}"
    )


def validate_result_uploads(frames, dag_name, project_id=PROJECT_ID):
    """Validate guarded result tables before any GCS overwrite."""
    client = bigquery.Client(project=project_id)
    for table_name in GUARDED_TABLES:
        if table_name not in frames:
            continue
        validate_upload_row_count(frames[table_name], table_name, dag_name, client)
