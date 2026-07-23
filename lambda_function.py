import os
from datetime import datetime, timedelta, timezone
import pathlib
from contextlib import closing
import urllib.request as request
from urllib.parse import urlsplit
import shutil
import glob
import pygrib
import numpy as np
import boto3
import json
import hashlib
import re
import time

from ModelHelpers import download_requested_products
from ModelHelpers import download_requested_products_contour_outline
from ModelHelpers import download_requested_global_dynamic_wind_products
from ModelHelpers import ContourProduct
from ModelHelpers import Product
from ModelHelpers import WindProduct

#=============================

dynamodb = boto3.client('dynamodb')
table_name = 'EvoWeather-ModelURLTable'

#=============================

product_table = {
    "2mTMP": Product(":TMP:2 m above ground:", 220, 330, "linear", "K"),
    "MSLP": Product(":PRMSL:mean sea level:", 84400, 110000, "linear", "Pa"),
}

product_table_wind = {
    "10mWIND": WindProduct([":UGRD:10 m above ground:", ":VGRD:10 m above ground:"], 0, 88, "linear", "m/s"),
}

product_table_contours_outlined = {
    "MSLMA-outlined": ContourProduct(":PRMSL:mean sea level:", np.arange(85000, 110000, 200).tolist(), "Pa", filled=False, major_labels=np.arange(85200, 110000, 400)),
}

#=============================

hafs_filename_pattern = re.compile(
    r"^(?P<storm_id>\d{2}[a-z])\.(?P<init_time>\d{10})\."
    r"(?P<model_family>hfs[ab])\.(?P<domain>parent|storm)\.atm\."
    r"f(?P<forecast_hour>\d{3})\.grb2\.idx$",
    re.IGNORECASE
)

hmon_filename_pattern = re.compile(
    r"^(?P<storm_name>[a-z][a-z0-9-]*?)(?P<storm_id>\d{2}[a-z])\."
    r"(?P<init_time>\d{10})\.hmonprs\.(?P<domain>d[123])\."
    r"(?P<resolution>0p\d+)\.f(?P<forecast_hour>\d{3})\.grb2\.idx$",
    re.IGNORECASE
)

hwrf_filename_pattern = re.compile(
    r"^(?P<storm_name>[a-z][a-z0-9-]*?)(?P<storm_id>\d{2}[a-z])\."
    r"(?P<init_time>\d{10})\.hwrfprs\."
    r"(?P<domain>global|synoptic|core|storm)\.(?P<resolution>0p\d+)\."
    r"f(?P<forecast_hour>\d{3})\.grb2\.idx$",
    re.IGNORECASE
)

#=============================

def respond_200():
    return {
        'statusCode': '200',
        'headers': {
            'Content-Type': 'application/json',
              "Access-Control-Allow-Origin": "*",
              "Access-Control-Allow-Credentials": True,
              "Access-Control-Allow-Headers": "Origin,Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,locale",
              "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
    }

def insert_item_dynamodb(model, model_init_time, forecast_hour):

    item = {'model': {'S': 'HURRICANE'},
            'time_string': {'S': f"{model}#{model_init_time.strftime('%m%d%y_%HZ')}_F{str(int(forecast_hour)).zfill(4)}"},
            'model_init_time': {'S': model_init_time.strftime('%m%d%y_%HZ')},
            'model_init_time_epoch': {'N': str(int(model_init_time.timestamp()))},
            'forecast_hour': {'N': str(int(forecast_hour))},
            'ttl': {'N': str(int(model_init_time.timestamp() + 86400*3))}}

    try:
        dynamodb.put_item(
            TableName=table_name,
            Item=item
        )
    except Exception as e:
        print(f"Error inserting item: {e}")
        raise Exception("Error inserting into dynamodb")

def parse_file_url(file_url):
    if not isinstance(file_url, str) or not file_url.endswith(".idx"):
        return None

    file = os.path.basename(urlsplit(file_url).path)

    match = hafs_filename_pattern.fullmatch(file)
    if match is not None:
        file_parts = match.groupdict()
        file_parts["model_family"] = file_parts["model_family"].upper()
    else:
        match = hmon_filename_pattern.fullmatch(file)
        if match is not None:
            file_parts = match.groupdict()
            file_parts["model_family"] = "HMON"
        else:
            match = hwrf_filename_pattern.fullmatch(file)
            if match is None:
                return None
            file_parts = match.groupdict()
            file_parts["model_family"] = "HWRF"

    file_parts["file"] = file
    file_parts["storm_id"] = file_parts["storm_id"].upper()
    file_parts["domain"] = file_parts["domain"].upper()
    file_parts["forecast_hour"] = int(file_parts["forecast_hour"])
    file_parts["model_init_time"] = datetime.strptime(file_parts.pop("init_time"), '%Y%m%d%H').replace(tzinfo=timezone.utc)
    file_parts["model"] = f"{file_parts['model_family']}/{file_parts['domain']}_{file_parts['storm_id']}"
    return file_parts

def grid_message_for_product(grbs, idx_lines, search_string):
    matches = [line_index for line_index, line in enumerate(idx_lines) if search_string in line]
    if len(matches) == 0:
        raise Exception(f"No match for search string: {search_string}")
    if len(matches) > 1:
        raise Exception(f"Duplicate matches for search string. Make the string more specific: {search_string}")
    return grbs[matches[0] + 1]

def grid_header_from_message(grb, file_parts):
    if grb.gridType != "regular_ll":
        raise Exception(f"Unsupported hurricane model grid type: {grb.gridType}")

    grid_header = {
        "grid_type": "regular_latlon",
        "grid_rows": int(grb.Nj),
        "grid_cols": int(grb.Ni),
        "rows": int(grb.Nj),
        "cols": int(grb.Ni) + 1,
        "data_column_offset": 1,
        "lat_start": float(grb.latitudeOfFirstGridPointInDegrees),
        "lat_end": float(grb.latitudeOfLastGridPointInDegrees),
        "lon_start": float(grb.longitudeOfFirstGridPointInDegrees),
        "lon_end": float(grb.longitudeOfLastGridPointInDegrees),
        "lat_step": float(grb.jDirectionIncrementInDegrees) * (1 if grb.jScansPositively else -1),
        "lon_step": float(grb.iDirectionIncrementInDegrees) * (-1 if grb.iScansNegatively else 1),
        "i_scans_negatively": bool(grb.iScansNegatively),
        "j_scans_positively": bool(grb.jScansPositively),
    }

    grid_string = json.dumps(grid_header, sort_keys=True, separators=(",", ":"))
    grid_header["grid_id"] = hashlib.sha256(grid_string.encode("utf-8")).hexdigest()[:16]
    grid_header["model_family"] = file_parts["model_family"]
    grid_header["storm_id"] = file_parts["storm_id"]
    grid_header["domain"] = file_parts["domain"]
    return grid_header

def lambda_handler(msg):

    time0 = time.time()
    print(f"Here is the msg: {msg}")

    body = json.loads(msg['Body'])
    file_url = body['file']
    file_parts = parse_file_url(file_url)

    if file_parts is None:
        print(f"Ignoring unsupported file: {file_url}")
        return respond_200()

    print(file_url)
    print("Will continue to work this code")

    model = file_parts["model"]
    model_init_time = file_parts["model_init_time"]
    forecast_hour = file_parts["forecast_hour"]

    current_time = datetime.now(timezone.utc)
    if current_time - model_init_time > timedelta(hours=72):
        print("Current time more than 72 hours ahead of model start time, responding 200 and exiting.")
        return respond_200()

    path = pathlib.Path("/tmp/lambda_data")
    path.mkdir(parents=True, exist_ok=True)

    files = glob.glob('/tmp/lambda_data/*')
    for old_file in files:
        os.remove(old_file)

    file = file_parts["file"][:-4]
    grib_url = file_url[:-4]
    local_dir = f"/tmp/lambda_data/{file}"

    with closing(request.urlopen(grib_url)) as r:
        with open(local_dir, "wb") as f:
            shutil.copyfileobj(r, f)

    with closing(request.urlopen(file_url)) as r:
        with open(f"{local_dir}.idx", "wb") as f:
            shutil.copyfileobj(r, f)

    with open(f"{local_dir}.idx") as f:
        idx_lines = np.array(f.readlines())
    grbs = pygrib.open(local_dir)

    grid_message = grid_message_for_product(grbs, idx_lines, product_table["2mTMP"].grb_lookup)
    header_fields = grid_header_from_message(grid_message, file_parts)

    print(f"Starting product downloads: {time.time() - time0}")
    download_requested_products(
        product_table,
        grbs,
        idx_lines,
        model,
        model_init_time=model_init_time,
        forecast_hour=forecast_hour,
        header_fields=header_fields
    )
    print(f"Standard products complete: {time.time() - time0}")

    if file_parts["model_family"] in ["HFSA", "HFSB"]:
        download_requested_global_dynamic_wind_products(
            product_table_wind,
            grbs,
            idx_lines,
            model,
            header_fields,
            6 if file_parts["domain"] == "PARENT" else 7,
            model_init_time=model_init_time,
            forecast_hour=forecast_hour
        )
        print(f"Wind products complete: {time.time() - time0}")

        download_requested_products_contour_outline(
            product_table_contours_outlined,
            grbs,
            idx_lines,
            model,
            model_init_time=model_init_time,
            forecast_hour=forecast_hour
        )
        print(f"Outlined contour products complete: {time.time() - time0}")

    insert_item_dynamodb(model, model_init_time, forecast_hour)

    print(f"Total time: {time.time() - time0}")
    return respond_200()


import multiprocessing as mp
import sys
import traceback

def _worker_handle_one(msg):
    try:
        lambda_handler(msg)
    except Exception:
        traceback.print_exc()
        sys.exit(2)

def main():
    sqs = boto3.client('sqs')
    model_sqs_url = os.environ["SQS_QUEUE_NAME"]
    print("Starting… polling SQS:", model_sqs_url)
    while True:
        resp = sqs.receive_message(
            QueueUrl=model_sqs_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
            VisibilityTimeout=60*7
        )
        for msg in resp.get("Messages", []):
            receipt = msg["ReceiptHandle"]

            p = mp.Process(target=_worker_handle_one, args=(msg,))
            p.start()
            p.join(timeout=60*6)

            if p.is_alive():
                print("Worker timed out; terminating")
                p.terminate()
                p.join(10)

            if p.exitcode == 0:
                sqs.delete_message(QueueUrl=model_sqs_url, ReceiptHandle=receipt)
            else:
                print(f"Worker nonzero exitcode={p.exitcode}; leaving message for retry")


if __name__ == "__main__":
    main()
