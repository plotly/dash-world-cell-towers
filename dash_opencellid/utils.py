from retrying import retry
import datashader as ds
from pyproj import Transformer

scheduler_url = "127.0.0.1:8786"


def compute_range_created_radio_hist(client):
    """
    Use Datashader to compute a 3D histogram of cell_towers_ddf, binned by the created,
    log10_range, and radio dimensions
    """
    cell_towers_ddf = client.get_dataset('cell_towers_ddf')
    created_bin_edges = client.get_dataset('created_bin_edges')
    created_bin_centers = client.get_dataset('created_bin_centers')
    min_log10_range = client.get_dataset('min_log10_range')
    max_log10_range = client.get_dataset('max_log10_range')

    created_bins = created_bin_edges.astype('int')

    cvs2 = ds.Canvas(
        # Specify created bins
        plot_width=len(created_bins) - 1,
        x_range=[min(created_bins), max(created_bins)],

        # Specify log10_range bins
        plot_height=20, y_range=[min_log10_range, max_log10_range]
    )
    agg = cvs2.points(cell_towers_ddf, x='created', y='log10_range', agg=ds.count_cat('radio'))

    # Set created index back to datetime values
    agg = agg.assign_coords(created=created_bin_centers)

    return agg


# Coordinate transformations
transformer_4326_to_3857 = Transformer.from_crs("epsg:4326", "epsg:3857")
transformer_3857_to_4326 = Transformer.from_crs("epsg:3857", "epsg:4326")


def epsg_4326_to_3857(coords):
    return [transformer_4326_to_3857.transform(*reversed(row)) for row in coords]


def epsg_3857_to_4326(coords):
    return [list(reversed(transformer_3857_to_4326.transform(*row))) for row in coords]


@retry(wait_exponential_multiplier=100, wait_exponential_max=2000, stop_max_delay=6000)
def get_dataset(client, name):
    return client.get_dataset(name)
