#!/bin/bash
# Add this directory to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:`dirname "$(realpath $0)"`
dask scheduler &
dask worker 127.0.0.1:8786 --nworkers 1 --nthreads 2 --local-directory work-dir &
python publish_data.py
python dash_opencellid/app.py
wait
