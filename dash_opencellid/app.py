# -*- coding: utf-8 -*-
import os
import time
from textwrap import dedent

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

import dask

import datashader as ds
import datashader.transfer_functions as tf
import numpy as np
import pandas as pd
from distributed import Client

from dash_opencellid.utils import (
    compute_range_created_radio_hist, epsg_4326_to_3857, get_dataset, scheduler_url
)

# Global initialization
client = None

def init_client():
    """
    This function must be called before any of the functions that require a client.
    """
    global client
    # Init client
    print(f"Connecting to cluster at {scheduler_url} ... ", end='')
    client = Client(scheduler_url)
    print("done")


# Radio constants
radio_categories = ['UMTS', 'LTE', 'GSM', 'CDMA']
radio_colors_list = ['green', 'red', 'blue', 'orange']
radio_colors = {cat: color for cat, color in zip(
    radio_categories, radio_colors_list
)}

# Colors
bgcolor = "#f3f3f1"  # mapbox light map land color
bar_bgcolor = "#b0bec5"  # material blue-gray 200
bar_unselected_color = "#78909c"  # material blue-gray 400
bar_color = "#546e7a"  # material blue-gray 600
bar_selected_color = "#37474f" # material blue-gray 800
bar_unselected_opacity = 0.8


# Figure template
row_heights = [150, 500, 300]
template = {'layout': {'paper_bgcolor': bgcolor, 'plot_bgcolor': bgcolor}}


def blank_fig(height):
    """
    Build blank figure with the requested height
    """
    return {
        'data': [],
        'layout': {
            'height': height,
            'template': template,
            'xaxis': {'visible': False},
            'yaxis': {'visible': False},
        }
    }


# Load mapbox token
token = os.getenv('MAPBOX_TOKEN')
if not token:
    token = open(".mapbox_token").read()


def build_modal_info_overlay(id, side, content):
    """
    Build div representing the info overlay for a plot panel
    """
    div = html.Div([  # modal div
        html.Div([  # content div
            html.Div([
                html.H4([
                    "Info",
                    html.Img(
                        id=f'close-{id}-modal',
                        src="assets/times-circle-solid.svg",
                        n_clicks=0,
                        className='info-icon',
                        style={'margin': 0},
                    ),
                ], className="container_title", style={'color': 'white'}),

                dcc.Markdown(
                    content
                ),
            ])
        ],
            className=f'modal-content {side}',
        ),
        html.Div(className='modal')
    ],
        id=f"{id}-modal",
        style={"display": "none"},
    )

    return div


# Build Dash layout
app = dash.Dash(__name__)

app.layout = html.Div(children=[
    html.Div([
        html.H1(children=[
            'World Cell Towers',
            html.A(
                html.Img(
                    src="assets/dash-logo.png",
                    style={'float': 'right', 'height': '50px'}
                ), href="https://dash.plot.ly/"),
        ], style={'text-align': 'left'}),
    ]),
    html.Div(children=[
        build_modal_info_overlay('indicator', 'bottom', dedent("""
            The _**Selected Towers**_ panel displays the number of cell towers
            that are currently selected. A tower is considered to be selected
            if it is currently visible in the _**Locations**_ map, and satisfies
            the selections applied in the _**Radio**_, _**Signal Range**_, and
            _**Construction Date**_ panels.

            The _**Reset All**_ button may be used to clear all selections and
            recenter the _**Locations**_ map view. 
            """)),
        build_modal_info_overlay('radio', 'bottom', dedent("""
            The _**Radio**_ panel displays a bar chart representing the
            number cell towers with each radio technology.
            
            The colored bars represent the number of towers that are currently selected
            in the _**Locations**_, _**Signal Range**_, and _**Construction Date**_
            panels. Note that cell tower counts are displayed using a log scale.
            
            Left-clicking on a colored bar selects the towers with the corresponding
            radio technology.  Holding the shift key while left-clicking extends the
            current selection. A left-click drag may also be used to select multiple
            bars using the box-selection tool. 
            
            The _**Clear Selection**_ button may be used to clear any selections
            applied in the _**Radio**_ panel, while leaving any selections applied in
            other panels unchanged. 
        """)),
        build_modal_info_overlay('map', 'bottom', dedent("""
            The _**Locations**_ panel displays the position of each selected tower on
            an interactive world map. Towers are colored by their radio technology with
            colors that match the bars in the _**Radio**_ panel.
            
            When 5000 or fewer towers are selected, hover tooltips containing
            tower details are available at each tower location. 
            
            Left-click drag to pan the map view, right-click drag to rotate and pitch
            the map view, and scroll to zoom in and out.  
            
            The _**Reset View**_ button may be used to reset the map to the original
            centered view, while leaving any selections applied in other panels
            unchanged. 
        """)),
        build_modal_info_overlay('range', 'top', dedent("""
            The _**Signal Range**_ panel displays a histogram of the signal range of
            each tower in the dataset.  The dark gray bars represent the set of towers
            in the current selection, while the light gray bars underneath represent
            all towers in the dataset.
            
            Left-click drag to select histogram bars using the box-selection tool.
            
            The _**Clear Selection**_ button may be used to clear any selections
            applied in the _**Signal Range**_ panel, while leaving any selections
            applied in other panels unchanged.
        """)),
        build_modal_info_overlay('created', 'top', dedent("""
            The _**Construction Date**_ panel displays a histogram of the construction
            date of each tower in the dataset.  The dark gray bars represent the set of
            towers in the current selection, while the light gray bars underneath
            represent all towers in the dataset.
            
            Left-click drag to select histogram bars using the box-selection tool.
            
            The _**Clear Selection**_ button may be used to clear any selections
            applied in the _**Construction Date**_ panel, while leaving any selections
            applied in other panels unchanged.
        """)),
        html.Div(children=[
            html.Div(children=[
                html.H4([
                    "Selected Towers",
                    html.Img(
                        id='show-indicator-modal',
                        src="assets/question-circle-solid.svg",
                        n_clicks=0,
                        className='info-icon',
                    ),
                ], className="container_title"),
                dcc.Loading(
                    dcc.Graph(
                        id='indicator-graph',
                        figure=blank_fig(row_heights[0]),
                        config={'displayModeBar': False},
                    ),
                    className='svg-container',
                    style={'height': 150},
                ),
                html.Div(children=[
                    html.Button("Reset All", id='clear-all', className='reset-button'),
                ]),
            ], className='six columns pretty_container', id="indicator-div"),
            html.Div(children=[
                html.H4([
                    "Radio",
                    html.Img(
                        id='show-radio-modal',
                        src="assets/question-circle-solid.svg",
                        className='info-icon',
                    ),
                ], className="container_title"),
                dcc.Graph(
                    id='radio-histogram',
                    figure=blank_fig(row_heights[0]),
                    config={'displayModeBar': False}
                ),
                html.Button("Clear Selection", id='clear-radio', className='reset-button'),
            ], className='six columns pretty_container', id="radio-div"),
        ]),
        html.Div(children=[
            html.H4([
                "Locations",
                html.Img(
                    id='show-map-modal',
                    src="assets/question-circle-solid.svg",
                    className='info-icon',
                ),
            ], className="container_title"),
            dcc.Graph(
                id='map-graph',
                figure=blank_fig(row_heights[1]),
                config={'displayModeBar': False},
            ),
            html.Button("Reset View", id='reset-map', className='reset-button'),
        ], className='twelve columns pretty_container',
            style={
                'width': '98%',
                'margin-right': '0',
            },
            id="map-div"
        ),
        html.Div(children=[
            html.Div(
                children=[
                    html.H4([
                        "Signal Range",
                        html.Img(
                            id='show-range-modal',
                            src="assets/question-circle-solid.svg",
                            className='info-icon',
                        ),
                    ], className="container_title"),
                    dcc.Graph(
                        id='range-histogram',
                        figure=blank_fig(row_heights[2]),
                        config={'displayModeBar': False}
                    ),
                    html.Button("Clear Selection", id='clear-range', className='reset-button'),
                ],
                className='six columns pretty_container', id="range-div"
            ),
            html.Div(
                children=[
                    html.H4([
                        "Construction Date",
                        html.Img(
                            id='show-created-modal',
                            src="assets/question-circle-solid.svg",
                            className='info-icon',
                        ),
                    ], className="container_title"),
                    dcc.Graph(
                        id='created-histogram',
                        config={'displayModeBar': False},
                        figure=blank_fig(row_heights[2]),
                    ),
                    html.Button("Clear Selection", id='clear-created', className='reset-button'),
                ],
                className='six columns pretty_container', id="created-div"
            ),
        ]),
    ]),
    html.Div(
        [
            html.H4('Acknowledgements', style={"margin-top": "0"}),
            dcc.Markdown('''\
 - Dashboard written in Python using the [Dash](https://dash.plot.ly/) web framework.
 - Parallel and distributed calculations implemented using the [Dask](https://dask.org/) Python library.
 - Server-side visualization of the location of all 40 million cell towers performed 
 using the [Datashader] Python library (https://datashader.org/).
 - Base map layer is the ["light" map style](https://www.mapbox.com/maps/light-dark/)
 provided by [mapbox](https://www.mapbox.com/).
 - Cell tower dataset provided by the [OpenCelliD Project](https://opencellid.org/) which is licensed under a
[_Creative Commons Attribution-ShareAlike 4.0 International License_](https://creativecommons.org/licenses/by-sa/4.0/).
 - Mapping from cell MCC/MNC to network operator scraped from https://cellidfinder.com/mcc-mnc.
 - Icons provided by [Font Awesome](https://fontawesome.com/) and used under the
[_Font Awesome Free License_](https://fontawesome.com/license/free). 
'''),
        ],
        style={
            'width': '98%',
            'margin-right': '0',
            'padding': '10px',
        },
        className='twelve columns pretty_container',
    ),
])

# Create show/hide callbacks for each info modal
for id in ['indicator', 'radio', 'map', 'range', 'created']:
    @app.callback([Output(f"{id}-modal", 'style'), Output(f"{id}-div", 'style')],
                  [Input(f'show-{id}-modal', 'n_clicks'),
                   Input(f'close-{id}-modal', 'n_clicks')])
    def toggle_modal(n_show, n_close):
        ctx = dash.callback_context
        if ctx.triggered and ctx.triggered[0]['prop_id'].startswith('show-'):
            return {"display": "block"}, {'zIndex': 1003}
        else:
            return {"display": "none"}, {'zIndex': 0}

# Create clear/reset button callbacks
@app.callback(
    Output('map-graph', 'relayoutData'),
    [Input('reset-map', 'n_clicks'), Input('clear-all', 'n_clicks')]
)
def reset_map(*args):
    return None


@app.callback(
    Output('radio-histogram', 'selectedData'),
    [Input('clear-radio', 'n_clicks'), Input('clear-all', 'n_clicks')]
)
def clear_radio_hist_selections(*args):
    return None


@app.callback(
    Output('range-histogram', 'selectedData'),
    [Input('clear-range', 'n_clicks'), Input('clear-all', 'n_clicks')]
)
def clear_range_hist_selections(*args):
    return None


@app.callback(
    Output('created-histogram', 'selectedData'),
    [Input('clear-created', 'n_clicks'), Input('clear-all', 'n_clicks')]
)
def clear_created_hist_selection(*args):
    return None


@app.callback(
    [Output('indicator-graph', 'figure'), Output('map-graph', 'figure'),
     Output('radio-histogram', 'figure'), Output('range-histogram', 'figure'),
     Output('created-histogram', 'figure')],
    [Input('map-graph', 'relayoutData'), Input('radio-histogram', 'selectedData'),
     Input('range-histogram', 'selectedData'), Input('created-histogram', 'selectedData')])
def update_plots(
        relayout_data, selected_radio, selected_range, selected_created,
):
    cell_towers_ddf = get_dataset(client, 'cell_towers_ddf')
    data_4326 = get_dataset(client, 'data_4326')
    data_center_4326 = get_dataset(client, 'data_center_4326')
    data_3857 = get_dataset(client, 'data_3857')

    t0 = time.time()
    coordinates_4326 = relayout_data and relayout_data.get('mapbox._derived', {}).get('coordinates', None)

    if coordinates_4326:
        lons, lats = zip(*coordinates_4326)
        lon0, lon1 = max(min(lons), data_4326[0][0]), min(max(lons), data_4326[1][0])
        lat0, lat1 = max(min(lats), data_4326[0][1]), min(max(lats), data_4326[1][1])
        coordinates_4326 = [
            [lon0, lat0],
            [lon1, lat1],
        ]
        coordinates_3857 = epsg_4326_to_3857(coordinates_4326)
        # position = {}
        position = {
            'zoom': relayout_data.get('mapbox.zoom', None),
            'center': relayout_data.get('mapbox.center', None)
        }
    else:
        position = {
            'zoom': 0.5,
            'pitch': 0,
            'bearing': 0,
            'center': {'lon': data_center_4326[0][0], 'lat': data_center_4326[0][1]}
        }
        coordinates_3857 = data_3857
        coordinates_4326 = data_4326

    new_coordinates = [
        [coordinates_4326[0][0], coordinates_4326[1][1]],
        [coordinates_4326[1][0], coordinates_4326[1][1]],
        [coordinates_4326[1][0], coordinates_4326[0][1]],
        [coordinates_4326[0][0], coordinates_4326[0][1]],
    ]

    x_range, y_range = zip(*coordinates_3857)
    x0, x1 = x_range
    y0, y1 = y_range

    # Build query expressions
    query_expr_xy = f"(x_3857 >= {x0}) & (x_3857 <= {x1}) & (y_3857 >= {y0}) & (y_3857 <= {y1})"
    query_expr_range_created_parts = []

    # Handle range selection
    range_slice = slice(None, None)
    if selected_range:
        log10_r0, log10_r1 = selected_range['range']['x']
        if log10_r1 < log10_r0:
            log10_r0, log10_r1 = log10_r1, log10_r0
        range_slice = slice(log10_r0, log10_r1)

        query_expr_range_created_parts.append(
            f"(log10_range >= {log10_r0}) & (log10_range <= {log10_r1})"
        )

    # Handle created selection
    created_slice = slice(None, None)
    if selected_created:
        created_dt0, created_dt1 = pd.to_datetime(selected_created['range']['x'])
        if created_dt1 < created_dt0:
            created_dt0, created_dt1 = created_dt1, created_dt0
        created_slice = slice(created_dt0, created_dt1)

        created0, created1 = pd.Series([created_dt0, created_dt1]).astype('int')
        query_expr_range_created_parts.append(
            f"(created >= {created0}) & (created <= {created1})"
        )

    # Get selected radio categories
    selected_radio_categories = radio_categories
    if selected_radio:
        selected_radio_categories = list(set(
            point['y'] for point in selected_radio['points']
        ))

    # Build dataframe containing rows that satisfy the range and created selections
    if query_expr_range_created_parts:
        query_expr_range_created = ' & '.join(query_expr_range_created_parts)
        ddf_selected_range_created = cell_towers_ddf.query(
            query_expr_range_created
        )
    else:
        ddf_selected_range_created = cell_towers_ddf

    # Build dataframe containing rows of towers within the map viewport
    ddf_xy = cell_towers_ddf.query(query_expr_xy) if query_expr_xy else cell_towers_ddf

    # Build map figure
    # Create datashader aggregation of x/y data that satisfies the range and created
    # histogram selections
    cvs = ds.Canvas(
        plot_width=700,
        plot_height=400,
        x_range=x_range, y_range=y_range
    )
    agg = cvs.points(
        ddf_selected_range_created, x='x_3857', y='y_3857', agg=ds.count_cat('radio')
    )

    # Downselect aggregation to include only the select radio categories
    if selected_radio_categories:
        agg = agg.sel(radio=selected_radio_categories)

    # Count the number of selected towers
    n_selected = int(agg.sum())

    # Build indicator figure
    n_selected_indicator = {
        'data': [{
            'type': 'indicator',
            'value': n_selected,
            'number': {
                'font': {
                    'color': '#263238'
                }
            }
        }],
        'layout': {
            'template': template,
            'height': 150,
            'margin': {'l': 10, 'r': 10, 't': 10, 'b': 10}
        }
    }

    if n_selected == 0:
        # Nothing to display
        lat = [None]
        lon = [None]
        customdata = [None]
        marker = {}
        layers = []
    elif n_selected < 5000:
        # Display each individual point using a scattermapbox trace. This way we can
        # give each individual point a tooltip
        ddf_small_expr = ' & '.join(
            [query_expr_xy] + [f'(radio in {selected_radio_categories})'] +
            query_expr_range_created_parts
        )
        ddf_small = cell_towers_ddf.query(ddf_small_expr)
        lat, lon, radio, log10_range, description, mcc, net, created, status = dask.compute(
            ddf_small.lat, ddf_small.lon, ddf_small.radio, ddf_small.log10_range,
            ddf_small.Description, ddf_small.mcc, ddf_small.net, ddf_small.created,
            ddf_small.Status
        )

        # Format creation date column for tooltip
        created = pd.to_datetime(created.tolist()).strftime('%x')

        # Build colorscale to give scattermapbox points the appropriate color
        radio_colorscale = [
            [v, radio_colors[cat]] for v, cat in zip(
                np.linspace(0, 1, len(radio.cat.categories)), radio.cat.categories
            )
        ]

        # Build array of the integer category codes to use as the numeric color array
        # for the scattermapbox trace
        radio_codes = radio.cat.codes

        # Build marker properties dict
        marker = {
            'color': radio_codes,
            'colorscale': radio_colorscale,
            'cmin': 0,
            'cmax': 3,
            'size': 5,
            'opacity': 0.6,
        }

        # Build customdata array for use in hovertemplate
        def to_str_unknown(cat_series):
            result = cat_series.astype(str)
            result[pd.isnull(cat_series)] = "Unknown"
            return result

        customdata = list(zip(
            radio.astype(str),
            ((10 ** log10_range)).astype(int),
            [s[:25] for s in to_str_unknown(description)],
            mcc,
            net,
            created,
            to_str_unknown(status),
        ))
        layers = []
    else:
        # Shade aggregation into an image that we can add to the map as a mapbox
        # image layer
        img = tf.shade(agg, color_key=radio_colors, min_alpha=100).to_pil()

        # Resize image to map size to reduce image blurring on zoom.
        img = img.resize((1400, 800))

        # Add image as mapbox image layer. Note that as of version 4.4, plotly will
        # automatically convert the PIL image object into a base64 encoded png string
        layers = [
            {
                "sourcetype": "image",
                "source": img,
                "coordinates": new_coordinates
            }
        ]

        # Do not display any mapbox markers
        lat = [None]
        lon = [None]
        customdata = [None]
        marker = {}

    # Build map figure
    map_graph = {
        'data': [{
            'type': 'scattermapbox',
            'lat': lat, 'lon': lon,
            'customdata': customdata,
            'marker': marker,
            'hovertemplate': (
                "<b>%{customdata[2]}</b><br>"
                "MCC: %{customdata[3]}<br>"
                "MNC: %{customdata[4]}<br>"
                "radio: %{customdata[0]}<br>"
                "range: %{customdata[1]:,} m<br>"
                "created: %{customdata[5]}<br>"
                "status: %{customdata[6]}<br>"
                "longitude: %{lon:.3f}&deg;<br>"
                "latitude: %{lat:.3f}&deg;<br>"
                "<extra></extra>"
            )
        }],
        'layout': {
            'template': template,
            'uirevision': True,
            'mapbox': {
                'style': "light",
                'accesstoken': token,
                'layers': layers,
            },
            'margin': {"r": 0, "t": 0, "l": 0, "b": 0},
            'height': 500,
            'shapes': [{
                'type': 'rect',
                'xref': 'paper',
                'yref': 'paper',
                'x0': 0,
                'y0': 0,
                'x1': 1,
                'y1': 1,
                'line': {
                    'width': 2,
                    'color': '#B0BEC5',
                }
            }]
        },
    }

    map_graph['layout']['mapbox'].update(position)

    # Use datashader to histogram range, created, and radio simultaneously
    agg_range_created_radio = compute_range_created_radio_hist(client)

    # Build radio histogram
    selected_radio_counts = agg_range_created_radio.sel(
        log10_range=range_slice, created=created_slice
    ).sum(['log10_range', 'created']).to_series()
    radio_histogram = build_radio_histogram(
        selected_radio_counts, selected_radio is None
    )

    # Build range histogram
    selected_range_counts = agg_range_created_radio.sel(
        radio=selected_radio_categories, created=created_slice
    ).sum(['radio', 'created']).to_series()
    range_histogram = build_range_histogram(
        selected_range_counts, selected_range is None
    )

    # Build created histogram
    selected_created_counts = agg_range_created_radio.sel(
        radio=selected_radio_categories, log10_range=range_slice
    ).sum(['radio', 'log10_range']).to_series()
    created_histogram = build_created_histogram(
        selected_created_counts, selected_created is None
    )

    print(f"Update time: {time.time() - t0}")
    return (
        n_selected_indicator, map_graph, radio_histogram,
        range_histogram, created_histogram
    )


# Helper function to build figures
def build_radio_histogram(selected_radio_counts, selection_cleared):
    """
    Build horizontal histogram of radio counts
    """
    total_radio_counts = get_dataset(client, 'total_radio_counts')

    selectedpoints = False if selection_cleared else None
    hovertemplate = '%{x:,.0}<extra></extra>'

    fig = {'data': [
        {'type': 'bar',
         'x': total_radio_counts.values,
         'y': total_radio_counts.index,
         'marker': {'color': bar_bgcolor},
         'orientation': 'h',
         "selectedpoints": selectedpoints,
         'selected': {'marker': {'opacity': 1, 'color': bar_bgcolor}},
         'unselected': {'marker': {'opacity': 1, 'color': bar_bgcolor}},
         'showlegend': False,
         'hovertemplate': hovertemplate,
         },
    ], 'layout': {
        'template': template,
        'barmode': 'overlay',
        'dragmode': 'select',
        'selectdirection': 'v',
        'clickmode': 'event+select',
        'selectionrevision': True,
        'height': 150,
        'margin': {'l': 10, 'r': 80, 't': 10, 'b': 10},
        'xaxis': {
            'type': 'log',
            'title': {'text': 'Count'},
            'range': [-1, np.log10(total_radio_counts.max() * 2)],
            'automargin': True,
        },
        'yaxis': {
            'type': 'category',
            'categoryorder': 'array',
            'categoryarray': radio_categories,
            'side': 'left',
            'automargin': True,
        },
    }}

    # Add selected bars in color
    fig['data'].append(
        {'type': 'bar',
         'x': selected_radio_counts.loc[total_radio_counts.index],
         'y': total_radio_counts.index,
         'orientation': 'h',
         'marker': {'color': [radio_colors[cat] for cat in total_radio_counts.index]},
         "selectedpoints": selectedpoints,
         'unselected': {'marker': {'opacity': 0.2}},
         'hovertemplate': hovertemplate,
         'showlegend': False})

    return fig


def build_range_histogram(selected_range_counts, selection_cleared):
    """
    Build histogram of log10_range values
    """
    total_range_counts = get_dataset(client, 'total_range_counts')

    selectedpoints = False if selection_cleared else None
    hovertemplate = (
        "count: %{y:,.0}<br>"
        "range: %{customdata:,} m<br>"
        "log<sub>10</sub>(range): %{x:.2f}<br>"
        "<extra></extra>"
    )
    fig = {'data': [
        {'type': 'bar',
         'x': total_range_counts.index,
         'y': total_range_counts.values,
         'customdata': (10 ** total_range_counts.index).astype('int'),
         'marker': {'color': bar_bgcolor},
         'hovertemplate': hovertemplate,
         "selectedpoints": selectedpoints,
         'unselected': {'marker': {'opacity': 1.0}},
         "hoverinfo": "y",
         'showlegend': False},
    ], 'layout': {
        'template': template,
        'barmode': 'overlay',
        'selectionrevision': True,
        'height': 300,
        'margin': {'l': 10, 'r': 10, 't': 10, 'b': 10},
        'xaxis': {
            'automargin': True,
            'title': {'text': 'log<sub>10</sub>(range)'}
        },
        'yaxis': {
            'type': 'log',
            'automargin': True,
            'title': {'text': 'Count'},
        },
        'selectdirection': 'h',
        'hovermode': 'closest',
        'dragmode': 'select',
    }}

    fig['data'].append({
        'type': 'bar',
        'x': selected_range_counts.index,
        'y': selected_range_counts.values,
        'customdata': ((10 ** selected_range_counts.index)).astype('int'),
        'marker': {'color': bar_color},
        'hovertemplate': hovertemplate,
        'selected': {'marker': {'color': bar_selected_color, 'opacity': 1.0}},
        'unselected': {'marker': {
            'color': bar_unselected_color, 'opacity': bar_unselected_opacity
        }},
        "selectedpoints": selectedpoints,
        "hoverinfo": "x+y",
        'showlegend': False
    })

    return fig


def build_created_histogram(selected_created_counts, selection_cleared):
    """
    Build histogram of creation date values
    """
    total_created_counts = get_dataset(client, 'total_created_counts')
    selectedpoints = False if selection_cleared else None
    hovertemplate = (
        "count: %{y:,.0}<br>"
        "year: %{x|%Y}<br>"
        "<extra></extra>"
    )

    fig = {
        'data': [
            {'type': 'bar',
             'x': total_created_counts.index,
             'y': total_created_counts.values,
             'marker': {'color': bar_bgcolor},
             "selectedpoints": selectedpoints,
             "hovertemplate": hovertemplate,
             'unselected': {'marker': {'opacity': 1.0}},
             "hoverinfo": "y",
             'showlegend': False
             },
        ],
        'layout': {
            'template': template,
            'barmode': 'overlay',
            'selectionrevision': True,
            'height': 300,
            'margin': {'l': 10, 'r': 10, 't': 10, 'b': 10},
            'xaxis': {
                'title': {'text': 'Date'},
                'automargin': True
            },
            'yaxis': {
                'title': {'text': 'Count'},
                'type': 'log',
                'automargin': True
            },
            'selectdirection': 'h',
            'dragmode': 'select',
            'hovermode': 'closest',
        }
    }

    fig['data'].append({
        'type': 'bar',
        "hoverinfo": "x+y",
        'x': selected_created_counts.index,
        'y': selected_created_counts.values,
        'marker': {'color': bar_color},
        "selectedpoints": selectedpoints,
        "hovertemplate": hovertemplate,
        'selected': {'marker': {'color': bar_selected_color, 'opacity': 1.0}},
        'unselected': {'marker': {
            'color': bar_unselected_color, 'opacity': bar_unselected_opacity
        }},
        'showlegend': False
    })

    return fig


# gunicorn entry point
def get_server():
    init_client()
    return app.server


if __name__ == '__main__':
    init_client()
    app.run_server(debug=True)
