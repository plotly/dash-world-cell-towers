#!/bin/bash
# Add this directory to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:`dirname "$(realpath $0)"`
dask-scheduler &
dask-worker 127.0.0.1:8786 --nprocs 1 --local-directory work-dir &
python publish_data.py
gunicorn "dash_opencellid.app:get_server()" --timeout 60 --workers 1
wait
