import os
import dask.dataframe as dd
import numpy as np
from distributed import Client
import dask
import pandas as pd

from dash_opencellid.utils import (
    compute_range_created_radio_hist, epsg_3857_to_4326, scheduler_url
)

if __name__ == '__main__':
    # Note: The creation of a Dask LocalCluster must happen inside the `__main__` block,
    # that is so much logic is defined here.
    print(f"Connecting to cluster at {scheduler_url} ... ", end='')
    client = Client(scheduler_url)
    print("done")

    # Load and preprocess dataset
    if os.path.isdir('./data/cell_towers.parq'):
        cell_towers_ddf = dd.read_parquet('./data/cell_towers.parq')
    else:
        cell_towers_ddf = dd.read_parquet('/data/cell_towers.parq')
    cell_towers_ddf['radio'] = cell_towers_ddf['radio'].cat.as_known()
    cell_towers_ddf['Description'] = cell_towers_ddf['Description'].cat.as_known()
    cell_towers_ddf['Status'] = cell_towers_ddf['Status'].cat.as_known()
    cell_towers_ddf['log10_range'] = np.log10(cell_towers_ddf['range'])

    # Select columns to persist
    cell_towers_ddf = cell_towers_ddf[[
        'radio', 'x_3857', 'y_3857', 'log10_range', 'created',  # Filtering
        'lat', 'lon', 'Description', 'Status', 'mcc', 'net'  # Hover info
    ]]

    # Persist and publish Dask dataframe in memory
    cell_towers_ddf = cell_towers_ddf.repartition(npartitions=8).persist()

    # Clear any published datasets
    for k in client.list_datasets():
        client.unpublish_dataset(k)

    client.publish_dataset(cell_towers_ddf=cell_towers_ddf)

    data_3857 = dask.compute(
        [cell_towers_ddf['x_3857'].min(), cell_towers_ddf['y_3857'].min()],
        [cell_towers_ddf['x_3857'].max(), cell_towers_ddf['y_3857'].max()],
    )
    data_center_3857 = [[
        (data_3857[0][0] + data_3857[1][0]) / 2.0,
        (data_3857[0][1] + data_3857[1][1]) / 2.0,
    ]]
    data_4326 = epsg_3857_to_4326(data_3857)
    data_center_4326 = epsg_3857_to_4326(data_center_3857)

    client.publish_dataset(data_3857=data_3857)
    client.publish_dataset(data_4326=data_4326)
    client.publish_dataset(data_center_3857=data_center_3857)
    client.publish_dataset(data_center_4326=data_center_4326)

    # Create bin edges
    quarter_bins = pd.date_range('2003', '2020', freq='QS')
    created_bin_edges = quarter_bins[0::4]
    created_bin_centers = quarter_bins[2::4]
    created_bins = created_bin_edges.astype('int')

    client.publish_dataset(created_bin_edges=created_bin_edges)
    client.publish_dataset(created_bin_centers=created_bin_centers)

    min_log10_range, max_log10_range = dask.compute(
        cell_towers_ddf['log10_range'].min(), cell_towers_ddf['log10_range'].max()
    )

    client.publish_dataset(min_log10_range=min_log10_range)
    client.publish_dataset(max_log10_range=max_log10_range)

    # Pre-compute histograms containing all observations
    total_range_created_radio_agg = compute_range_created_radio_hist(client)
    total_radio_counts = total_range_created_radio_agg.sum(
        ['log10_range', 'created']).to_series()
    total_range_counts = total_range_created_radio_agg.sum(
        ['radio', 'created']).to_series()
    total_created_counts = total_range_created_radio_agg.sum(
        ['log10_range', 'radio']).to_series()

    client.publish_dataset(total_radio_counts=total_radio_counts)
    client.publish_dataset(total_range_counts=total_range_counts)
    client.publish_dataset(total_created_counts=total_created_counts)
