import os
import logging

from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.providers.google.cloud.operators.bigquery import BigQueryCreateExternalTableOperator, BigQueryInsertJobOperator
from airflow.providers.google.cloud.transfers.gcs_to_gcs import GCSToGCSOperator

PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BUCKET = os.environ.get("GCP_GCS_BUCKET")

path_to_local_home = os.environ.get("AIRFLOW_HOME", "/opt/airflow/")
BIGQUERY_DATASET = os.environ.get("BIGQUERY_DATASET", 'trips_data_all')

DATASET = "tripdata"
COLOUR_RANGE = {'yellow': 'tpep_pickup_datetime', 'green': 'lpep_pickup_datetime'}
INPUT_PART = "raw"
INPUT_FILETYPE = "parquet"

default_args = {
    "owner": "airflow",
    "start_date": days_ago(1),
    "depends_on_past": False,
    "retries": 1,
}

with DAG(
    dag_id="gcs_to_bq_dag",
    schedule_interval="@daily",
    default_args=default_args,
    catchup=False,
    max_active_runs=1,
    tags=['dtc-de'],
) as dag:

    for colour, ds_col in COLOUR_RANGE.items():
        gcs_to_gcs_task = GCSToGCSOperator(
            task_id=f'move_{colour}_{DATASET}_task',
            source_bucket=BUCKET,
            source_object=f'{INPUT_PART}/{colour}_{DATASET}*.{INPUT_FILETYPE}',
            destination_bucket=BUCKET,
            destination_object=f'{colour}/{colour}_{DATASET}',
            move_object=True,
        )

        gcs_to_bq_ext_task = BigQueryCreateExternalTableOperator(
            task_id=f"bq_{colour}_{DATASET}_external_table_task",
            table_resource={
                "tableReference": {
                    "projectId": PROJECT_ID,
                    "datasetId": BIGQUERY_DATASET,
                    "tableId": f"{colour}_{DATASET}_external_table",
                },
                "externalDataConfiguration": {
                    "autodetect":True,
                    "sourceFormat": f"{INPUT_FILETYPE.upper()}",
                    "sourceUris": [f"gs://{BUCKET}/{colour}/*"],
                },
            },
        )

        DROP_EHAIL = ""
        if colour == "green":
            DROP_EHAIL = " EXCEPT (ehail_fee)"

        CREATE_BQ_TBL_QUERY = (
                f"CREATE OR REPLACE TABLE {BIGQUERY_DATASET}.{colour}_{DATASET} \
                PARTITION BY DATE({ds_col}) \
                AS \
                SELECT *{DROP_EHAIL} FROM {BIGQUERY_DATASET}.{colour}_{DATASET}_external_table;"
            )

        bq_ext_part_task = BigQueryInsertJobOperator(
            task_id=f"bq_create_{colour}_{DATASET}_partitioned_table_task",
            configuration={
                "query":{
                    "query": CREATE_BQ_TBL_QUERY,
                    "useLegacySql": False,   
                }
            },
        )


        gcs_to_gcs_task >> gcs_to_bq_ext_task >> bq_ext_part_task