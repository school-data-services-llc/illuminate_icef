import requests
import pandas as pd
import json
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

token_url_illuminate = 'https://icefps.illuminateed.com/live/'
base_url_illuminate = 'https://icefps.illuminateed.com/live/rest_server.php/Api/'
current_date = datetime.now()
current_date = current_date.strftime('%Y-%m-%d')
REQUEST_TIMEOUT = 60  # seconds; avoids indefinite hangs that surface as Read timed out
#Currently have url_args hardcoded in each function param to be date filtered


def get_all_assessments_metadata(access_token):
    # Set the initial page and an empty DataFrame to store all results
    page = 1
    all_results = pd.DataFrame()

    #To ensure all pages are looped through properly
    while True:

        #Base URL and headers for API requests
        url_ext = f'Assessments/?page={page}&limit=1000'
        headers = {"Authorization": f"Bearer {access_token}"}

        logging.info(f'Fetching data from {base_url_illuminate + url_ext}')

        try:
            # Make the API request with the current page number
            response = requests.get(
                base_url_illuminate + url_ext.format(url_ext),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()  # Raise exception for HTTP errors
            
            results = json.loads(response.content)

            # Check if the required keys are in the response
            if 'results' not in results or 'num_pages' not in results:
                logging.error(f"Unexpected API response format: {results}")
                break

            logging.info(f'Here is the total num of pages on this endpoint {results["num_pages"]}')

            # Convert the results of the current page to a DataFrame and append to all_results
            page_results = pd.DataFrame(results['results'])
            all_results = pd.concat([all_results, page_results], ignore_index=True)

            # Check if we've retrieved all pages
            if page >= results['num_pages']:
                logging.info(f'Looped through {page} pages. Results for func get_all_assessments_metadata output into DataFrame')
                break

            # Move to the next page
            page += 1

        except requests.RequestException as e:
            logging.error(f"Error fetching page {page}: {e}")
            break
        except KeyError as e:
            logging.error(f"Key error: {e}")
            break


    assessment_id_list = list(all_results['assessment_id'].unique())
    return(all_results, assessment_id_list)


def get_single_assessment(access_token, _id, standard_or_no_standard, start_date, end_date_override=None):
    # Set the initial page and an empty DataFrame to store all results

    effective_end_date = end_date_override if end_date_override else current_date

    page = 1
    all_results = pd.DataFrame()

    url_args = f'?page={page}&assessment_id={_id}&limit=1000&date_taken_start={start_date}&date_taken_end={effective_end_date}'
    

    # Determine the endpoint based on the standard_or_no_standard parameter
    if standard_or_no_standard == 'No_Standard':
        url_ext = f'AssessmentAggregateStudentResponses/{url_args}'
    elif standard_or_no_standard == 'Standard':
        url_ext = f'AssessmentAggregateStudentResponsesStandard/{url_args}'
    else:
        print('Wrong variable for standard_or_no_standard')
        return None  # Exit the function if the parameter is incorrect
    
    logging.info(f'Here is the url_args for the get_single_asssessment function {url_ext}')

    headers = {
        "Authorization": f"Bearer {access_token}"
    }


    while True:
        # Make the API request with the current page number
        response = requests.get(
            base_url_illuminate + url_ext,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

        # Check if the response is successful
        if response.status_code != 200:
            logging.error(f"Error fetching page {page}: {response.status_code}")
            break

        # Parse the response content
        results = json.loads(response.content)

        # Convert the results of the current page to a DataFrame and append to all_results
        page_results = pd.DataFrame(results['results'])
        all_results = pd.concat([all_results, page_results], ignore_index=True)

        # Check if we've retrieved all pages
        if page >= results.get('num_pages', 1):  # Default to 1 if 'num_pages' is not present
            logging.info(f'Looped through {page} pages for assessment ID {_id}. Results output into DataFrame.')
            break

        # Move to the next page
        page += 1
        # Update the URL for the next page
        url_ext = f'AssessmentAggregateStudentResponses{"Standard" if standard_or_no_standard == "Standard" else ""}/{url_args}'

    return all_results



def get_assessment_scores(access_token, _id, standard_or_no_standard, start_date, end_date_override=None):

    effective_end_date = end_date_override if end_date_override else current_date
    

    # Initialize variables
    page = 1
    logging_list = []  # List to store logging information
    df_results_list = []  # List to collect results DataFrames
    headers = {
        "Authorization": f"Bearer {access_token}"
    }


    while True:
        # Update the URL arguments to reflect the current page number
        url_args = f'?page={page}&assessment_id={_id}&limit=1000&date_taken_start={start_date}&date_taken_end={effective_end_date}'

        # Determine the endpoint based on the standard_or_no_standard parameter
        if standard_or_no_standard == 'No_Standard':
            url_ext = f'AssessmentAggregateStudentResponses/{url_args}'
        elif standard_or_no_standard == 'Standard':
            url_ext = f'AssessmentAggregateStudentResponsesStandard/{url_args}'
        elif standard_or_no_standard == 'Group':
            url_ext = f'AssessmentAggregateStudentResponsesGroup/{url_args}'
        else:
            print('Wrong variable for standard_or_no_standard')
            return None, None  # Exit the function if the parameter is incorrect
        
        
        logging.debug(base_url_illuminate + url_ext)
        
        response = requests.get(
            base_url_illuminate + url_ext,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        r = response.status_code
        logging.debug(f'The status code for assessment_id {_id} is {r}')
       


        # Handle successful API response
        if r == 200:
            results = json.loads(response.content)
            num_results = results['num_results']
            num_pages = results['num_pages']
            logging.debug(f'Here is the num of pages for {_id} id - {num_pages} pages')

            if num_results == 0:
                # Log and exit if no results are found
                d = [_id, standard_or_no_standard, r, '', num_pages, num_results]
                logging_list.append(d)
                logging.debug(f'Results are NOT present for _id {_id}, num_results {num_results}, page {page}')
                break
            else:
                # Process and store the results
                logging.debug(f'Results are present for _id {_id}, num_results {num_results}, page {page}')
                df_page_results = pd.DataFrame(results['results'])
                df_page_results = df_page_results.sort_values(by='date_taken')
                df_page_results.reset_index(drop=True, inplace=True)
                df_page_results['percent_correct'] = df_page_results['percent_correct'].astype(float).round().astype(int)
                df_page_results['date_taken'] = pd.to_datetime(df_page_results['date_taken'])
                df_page_results['standard_no_standard'] = standard_or_no_standard
                df_results_list.append(df_page_results)

                if page == 1:  # Record details from the first page if there are results
                    title = df_page_results.iloc[0]['title']
                    d = [_id, standard_or_no_standard, r, title, num_pages, num_results]
                    logging_list.append(d)
        else:
            # Log unsuccessful API call and raise so the parallel retry pass can re-fetch
            num_pages = 0
            num_results = 0
            logging.error(
                "API call was not successful for %s; status=%s, url=%s, body=%s",
                _id,
                r,
                base_url_illuminate + url_ext,
                response.text[:500],
            )
            d = [_id, standard_or_no_standard, r, '', num_pages, num_results]
            logging_list.append(d)
            response.raise_for_status()

        # Check if all pages have been retrieved
        if page >= num_pages:
            logging.debug(f'Completed fetching for assessment ID {_id}.')
            break

        # Increment the page number for the next iteration
        page += 1

    # Concatenate all DataFrames in the list into a single DataFrame
    df_result = pd.concat(df_results_list, ignore_index=True) if df_results_list else pd.DataFrame()
    t = pd.DataFrame(logging_list, columns=['Assessment_ID', 'standard_no_standard', 'Status_Code', 'Assessment_Name', 'Num_of_Pages', 'Num_Of_Tests'])

    return df_result, t


def parallel_get_assessment_scores_threaded(
    access_token, assessment_id_list, standard_or_no_standard, start_date,
    end_date_override=None, max_workers=None
):
    """
    Parallelize API calls using threads (best for I/O-bound tasks like HTTP requests).
    Pass 1: all IDs. Pass 2: retry only IDs that raised (timeouts / HTTP errors).
    """
    logging.info(
        f"Starting parallel_get_assessment_scores_threaded with start_date={start_date}, "
        f"end_date_override={end_date_override}"
    )

    if max_workers is None:
        max_workers = min(32, (os.cpu_count() or 1) + 4)

    def fetch(_id):
        return get_assessment_scores(
            access_token, _id, standard_or_no_standard, start_date, end_date_override
        )

    def run_pass(ids, pass_label):
        results = []
        logs = []
        failed_ids = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {executor.submit(fetch, _id): _id for _id in ids}
            for future in as_completed(future_to_id):
                _id = future_to_id[future]
                try:
                    df_result, t = future.result()
                    results.append(df_result)
                    logs.append(t)
                except Exception as e:
                    logging.error(f"Error fetching assessment ID {_id} ({pass_label}): {e}")
                    failed_ids.append(_id)

        return results, logs, failed_ids

    all_results, all_logs, failed_ids = run_pass(assessment_id_list, "pass 1")

    if failed_ids:
        logging.info(
            f"Retrying {len(failed_ids)} failed assessment IDs for {standard_or_no_standard}"
        )
        retry_results, retry_logs, still_failed = run_pass(failed_ids, "pass 2 retry")
        all_results.extend(retry_results)
        all_logs.extend(retry_logs)
        if still_failed:
            preview = still_failed[:20]
            logging.error(
                f"{len(still_failed)} assessment IDs still failed after retry "
                f"for {standard_or_no_standard}. First {len(preview)}: {preview}"
            )
        else:
            logging.info(
                f"All previously failed assessment IDs succeeded on retry for {standard_or_no_standard}"
            )
    else:
        logging.info(f"No failed assessment IDs on pass 1 for {standard_or_no_standard}")

    final_df = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    final_logs = pd.concat(all_logs, ignore_index=True) if all_logs else pd.DataFrame()
    return final_df, final_logs


def loop_through_assessment_scores(access_token, id_list, standard_or_no_standard, start_date, end_date_override=None):

    print(f'The length of the ID_list is {len(id_list)}')

    df_list = []
    t_list = []

    logging.info(f"Pipeline starting with start_date={start_date}, end_date_override={end_date_override}")

    # Iterate over the list of IDs and append df and t to their respective lists
    for _id in id_list: #Coming from config
        df, t = get_assessment_scores(access_token, _id, standard_or_no_standard, start_date, end_date_override)
        df_list.append(df)
        t_list.append(t)
        
    test_results = pd.concat(df_list)
    log_results = pd.concat(t_list)
    log_results['standard_no_standard'] = standard_or_no_standard
    log_results['last_update'] = pd.Timestamp.today().date()
    test_results['last_update'] = pd.Timestamp.today().date()
    test_results = test_results.reset_index(drop = True)

    logging.info(f'Returning the frame and log for loop_through_assessment_scores {standard_or_no_standard}')
 
    return(test_results, log_results)


def add_missing_assessments(assessment_id_list, new_ids):
    unique_assessment_ids = set(assessment_id_list)  # Convert to set for faster lookups
    for assessment_id in new_ids:
        if assessment_id not in unique_assessment_ids:
            unique_assessment_ids.add(assessment_id)
            logging.info(f'Adding missing assessment_id - {assessment_id}')
    return list(unique_assessment_ids)  # Convert back to list
