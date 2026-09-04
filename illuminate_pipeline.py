import os
# Docker default; allow local override via env (do not overwrite if already set)
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "/app/icef-437920.json")
import logging
import sys
from datetime import datetime
import pandas as pd
from modules.auth import *
from modules.assessments_endpoints import *
from modules.frame_transformations import *
from gcp_utils_sds import buckets, yoy, append_assessment_titles
from modules.gcs_upload_guards import validate_result_uploads
import multiprocessing
import psutil



# Configure logging to use StreamHandler for stdout
logging.basicConfig(
    level=logging.INFO,  # Adjust as needed (e.g., DEBUG, WARNING)
    format="%(asctime)s - %(message)s",  # Log format
    datefmt="%d-%b-%y %H:%M:%S",  # Date format
    handlers=[
        logging.StreamHandler(sys.stdout)  # Direct logs to stdout
    ],
    force=True  # Ensures existing handlers are replaced
)

def get_assessment_results(years_data, start_date, end_date_override=None):
    logging.info('\n\n-------------New Illuminate Operations Logging Instance')
    logging.info(f"Available CPUs: {multiprocessing.cpu_count()}")
    logging.info(f"Available RAM: {round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB")
    logging.info(f'Years Data variable passed in is {years_data}')

    effective_end_date = end_date_override or datetime.now().strftime('%Y-%m-%d')
    skip_score_fetch = start_date > effective_end_date
    if skip_score_fetch:
        logging.info(
            f"start_date ({start_date}) is after end_date ({effective_end_date}). "
            "Skipping current-year score fetch; will append historical years only."
        )

    token_session = IlluminateTokenSession()

    assessments_metadata, assessment_id_list = get_all_assessments_metadata(token_session)
    assessment_id_list = list(set(assessment_id_list))
    if '115538' in assessment_id_list: #Faulty assessment_id that causes issues.
        assessment_id_list.remove('115538')

    logging.info(f'Here is the length of the assessment_id_list variable {len(assessment_id_list)}')

    if skip_score_fetch:
        assessment_results_group = pd.DataFrame()
        assessment_results_combined = pd.DataFrame()
        illuminate_assessment_results = pd.DataFrame()
    else:
        assessment_results_group, log_results_group = parallel_get_assessment_scores_threaded(token_session, assessment_id_list, 'Group', start_date, end_date_override)
        test_results_standard, log_results_standard = parallel_get_assessment_scores_threaded(token_session, assessment_id_list, 'Standard', start_date, end_date_override)
        test_results_no_standard, log_results_no_standard = parallel_get_assessment_scores_threaded(token_session, assessment_id_list, 'No_Standard', start_date, end_date_override)

        logging.info(f'Here is the length of the assessment_results_group variable {len(assessment_results_group)}')
        logging.info(f'Here is the length of the test_results_standard variable {len(test_results_standard)}')
        logging.info(f'Here is the length of the test_results_no_standard variable {len(test_results_no_standard)}')

        if (
            len(assessment_results_group) == 0
            and len(test_results_standard) == 0
            and len(test_results_no_standard) == 0
        ):
            logging.info(
                "All current-year assessment result frames are empty. "
                "Continuing with historical append only."
            )
            assessment_results_group = pd.DataFrame()
            assessment_results_combined = pd.DataFrame()
            illuminate_assessment_results = pd.DataFrame()
        else:
            assessment_results_combined = bring_together_test_results(test_results_no_standard, test_results_standard)
            illuminate_assessment_results = create_test_results_view(assessment_results_combined, years_data)

            assessment_results_group['year'] = years_data
            assessment_results_combined['year'] = years_data
            illuminate_assessment_results['year'] = years_data

    logging.info("Bringing together with prior years")

    #send to curriculum labels table (skip when no current-year view rows)
    if len(illuminate_assessment_results) > 0:
        append_assessment_titles(
            frame=illuminate_assessment_results,
            project_id="icef-437920",
            data_source="illuminate",
        )

    appender = yoy.YearlyDataAppender(
        project_id="icef-437920",
        dataset_id="illuminate",
        bucket_name="historicalbucket-icefschools-1"
    )

    frames = {
        "assessment_results_group": assessment_results_group,
        "assessment_results_combined": assessment_results_combined,
        "illuminate_assessment_results": illuminate_assessment_results,
    }
    historical_years = ["23-24", "24-25", "25-26"]

    for table_name, current_df in frames.items():
        frames[table_name] = appender.load_and_append(
            table_name=table_name,
            blob_paths_old=[
                f"illuminate/{table_name}_{year}.csv" for year in historical_years
            ],
            current_df=current_df,
        )

    logging.info(f'Sending data for {years_data} school year')
    bucket_name = "illuminatebucket-icefschools-1"
    project_id = "icef-437920"

    validate_result_uploads(frames, dag_name="illuminate_dag", project_id=project_id)

    frames["assessments_metadata"] = assessments_metadata
    for frame_name, frame in frames.items():
        buckets.send_to_gcs(
            bucket_name=bucket_name,
            save_path="",
            frame=frame,
            frame_name=f"{frame_name}.csv",
            project_id=project_id,
            dag_name='illuminate_dag',
        )

    return frames



get_assessment_results(
    years_data=os.getenv('YEARS_DATA', '26-27'),
    start_date=os.getenv('START_DATE', '2026-08-01'),
)
