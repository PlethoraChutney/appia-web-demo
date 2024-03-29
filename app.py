import dash
from dash import dcc
from dash import html
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import parse_qs
import pandas as pd
from appia.processors.experiment import Experiment, concat_experiments

url_basename = '/'
app = dash.Dash(__name__, url_base_pathname = url_basename)
server = app.server

hplc_one = Experiment('HPLC Example 1')
hplc_two = Experiment('HPLC Example 2')
fplc_one = Experiment('FPLC Example 1')
fplc_two = Experiment('FPLC Example 2')

hplc_one = pd.read_csv('data/hplc.csv')
hplc_two = pd.read_csv('data/hplc2.csv')
fplc_one = pd.read_csv('data/fplc.csv')
fplc_two = pd.read_csv('data/fplc2.csv')

class Database(object):
    def get_exp(self, exp_name):
        exp = Experiment(exp_name)
        is_real_exp = True
        if exp_name == 'HPLC_Example_1':
            exp.hplc = hplc_one.copy()
        elif exp_name == 'HPLC_Example_2':
            exp.hplc = hplc_two.copy()
        elif exp_name == 'FPLC_Example_1':
            exp.fplc = fplc_one
        elif exp_name == 'FPLC_Example_2':
            exp.fplc = fplc_two
        else:
            is_real_exp = False

        return exp if is_real_exp else None

db = Database()

exp_options = [
    'HPLC_Example_1', 
    'HPLC_Example_2', 
    'FPLC_Example_1', 
    'FPLC_Example_2'
]

channel_dict = {
    '2475ChA ex280/em350': 'Trp',
    '2475ChB ex488/em509': 'GFP'
}

def exp_list_from_pathname(pathname):
    path_string = pathname.replace(url_basename, '')
    return path_string.split('+')

def get_experiments(experiment_name_list):
    if len(experiment_name_list) == 1:
        exp = db.get_exp(experiment_name_list[0].replace('%20', ' '))
    else:
        exp_list = [db.get_exp(x.replace('%20', ' ')) for x in experiment_name_list]
        exp = concat_experiments(exp_list)

    return exp

def make_combined_table(exp):
    if exp.fplc is not None:
        hplc_df = exp.hplc.copy()
        fplc_as_h = exp.fplc.loc[exp.fplc['Channel'] == 'mAU'][['mL', 'Sample', 'Normalization', 'Value']].copy()
        fplc_as_h['Sample'] = 'Preparative: ' + fplc_as_h['Sample']

        f_per_channel = []

        for channel in set(hplc_df['Channel']):
            ch_f = fplc_as_h.copy()
            ch_f['Channel'] = channel
            f_per_channel.append(ch_f)

        fplc_as_h = pd.concat(f_per_channel)
        hplc_df = pd.concat([hplc_df, fplc_as_h])
    else:
        hplc_df = exp.hplc

    return hplc_df

def get_hplc_graphs(
    exp, view_range = None,
    x_ax = 'mL', overlay = False
):
    exp.rename_channels(channel_dict)
    raw_graphs = []

    if overlay:
        x_ax = 'mL'
        hplc_df = make_combined_table(exp)
    else:
        hplc_df = exp.hplc

    hplc_df.dropna(subset=['Value'], inplace = True)

    print(hplc_df)


    if len(hplc_df['Sample'].unique()) > 10:
        disc_color_scheme = px.colors.qualitative.Alphabet
    else:
        disc_color_scheme = px.colors.qualitative.Plotly

    for norm in ['Signal', 'Normalized']:

        fig = px.line(
            data_frame = hplc_df.loc[hplc_df['Normalization'] == norm],
            x = x_ax,
            y = 'Value',
            color = 'Sample',
            facet_row = 'Channel',
            template = 'plotly_white',
            color_discrete_sequence=disc_color_scheme
        )

        if norm == 'Normalized':
            try:
                # without this, your channels are stuck using the same yaxis range
                fig.layout.yaxis1.update(matches = None, range = [0,1])
                fig.layout.yaxis2.update(matches = None, range = [0,1])
                fig.layout.yaxis3.update(matches = None, range = [0,1])
                fig.layout.yaxis4.update(matches = None, range = [0,1])
            except AttributeError:
                # if the trace only has one channel, it doesn't have yaxis2
                pass
        else:
            try:
                # without this, your channels are stuck using the same yaxis range
                fig.layout.yaxis1.update(matches = None)
                fig.layout.yaxis2.update(matches = None)
                fig.layout.yaxis3.update(matches = None)
                fig.layout.yaxis4.update(matches = None)
            except AttributeError:
                # if the trace only has one channel, it doesn't have yaxis2
                pass

        # remove 'Channel=' from the facet labels
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

        if x_ax == 'Time':
            fig.update_layout(xaxis_title = 'Time (min)')

        raw_graphs.append(fig)

        if view_range is not None:
            fig.update_xaxes(autorange = False, range = view_range)

    return raw_graphs

def get_fplc_graphs(exp):
    fplc = exp.fplc

    if fplc is None:
        return None


    samples = set(fplc['Sample'])

    # Using GO primitives b/c plotly express creates traces which are zero
    # outside the defined fraction region, resulting in strange fill behavior
    # when non-continuous fractions are selected.
    
    if len(samples) == 1:
        fplc = fplc.loc[(fplc.Normalization == 'Signal') & (fplc.Channel == 'mAU')]
        fplc_graph = go.Figure()
        for frac in set(fplc['Fraction']):
            fplc_graph.add_trace(
                go.Scatter(
                    x = fplc[fplc.Fraction == frac]['mL'],
                    y = fplc[fplc.Fraction == frac]['Value'],
                    mode = 'lines',
                    fill = 'tozeroy',
                    visible = 'legendonly',
                    # if you don't rename them, fraction numbering is off by one
                    name = f'Fraction {frac}'
                )
            )
        fplc_graph.add_trace(
            # want the overall FPLC curve as a separate trace so that it stays present
            # to give overall sense of quality of trace
            go.Scatter(
                x = fplc['mL'],
                y = fplc['Value'],
                mode = 'lines',
                showlegend = False,
                hovertemplate = 'mAU: %{y}<br>Volume: %{x}<br>Fraction: %{text}',
                text = fplc['Fraction'],
                line = {'color': 'black'}
            )
        )
    else:
        fplc = fplc.loc[(fplc.Channel == 'mAU')]
        fplc_graph = px.line(
            data_frame = fplc,
            x = 'mL',
            y = 'Value',
            color = 'Sample',
            facet_row = 'Normalization',
            hover_data = ['Value', 'mL', 'Fraction'],
            template = 'plotly_white'
        )
        try:
            fplc_graph.layout.yaxis2.update(matches = None)
        except AttributeError:
            pass
        # remove 'Channel=' from the facet labels
        fplc_graph.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))


    fplc_graph.update_layout(template = 'plotly_white')
    fplc_graph.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

    fplc_graph.update_layout(
        xaxis_title = 'Retention Volume (mL)',
        yaxis_title = 'Signal'
    )
    return fplc_graph

def get_plotly(exp, view_range = None, x_ax = 'mL', format_val = 'png', overlay = False):
    combined_graphs = {}
    html_graphs = []
    
    if exp.hplc is not None:
        combined_graphs['Signal'], combined_graphs['Normalized'] = get_hplc_graphs(exp, view_range, x_ax, overlay)


    if exp.fplc is not None:
        combined_graphs['FPLC'] = get_fplc_graphs(exp)

    for data_type in combined_graphs.keys():
        html_graphs.extend([
                html.H5(
                    children = data_type,
                    style = {'textAlign': 'center'}
                ),
                dcc.Graph(
                    style={'height': 600},
                    id=f'data-{data_type}',
                    figure=combined_graphs[data_type],
                    config = {
                        'toImageButtonOptions': {
                            'format': format_val,
                            'width': 1000,
                            'height': 800
                        }
                    }
                )
            ])

    return html_graphs

def parse_query(q_string):
    q_string = parse_qs(q_string.replace('?', ''))

    if 'norm-range' in q_string.keys():
        try:
            norm_range = q_string['norm-range'][0].split('-')
            norm_range = [float(x) for x in norm_range]
        except ValueError:
            norm_range = None
    else:
        norm_range = None

    if 'view-range' in q_string.keys():
        try:
            view_range = q_string['view-range'][0].split('-')
            view_range = [float(x) for x in view_range]
        except ValueError:
            view_range = None
    else:
        view_range = None

    return norm_range, view_range

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Appia Traces</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

def serve_layout():
    return html.Div(
        className = 'container',
        children=[
            dcc.Location(id='root-location', refresh=False),
            html.Div(
                className = 'graph-title',
                children = [
                html.H1(
                    children='Appia Chromatography Viewer',
                    style = {'textAlign': 'center'}
                ),
                html.Div(
                    children='Simple traces from the comfort of your bench.',
                    style = {'textAlign': 'center'}
                ),
                html.Div(
                    children=[html.H4(children=html.Div(id='output-container'))],
                    style = {'textAlign': 'center'}
                )
                ]
            ),
            # sidebar div
            html.Div(
                className = 'sidebar',
                style = {'text-align': 'center'},
                children = [
                    html.H5(
                        style = {'paddingTop': '10px', 'textAlign': 'center'},
                        children = 'Pick experiment:'
                    ),
                    html.Div(
                        style = {'padding-top': '10px', 'padding-bottom': '10px'},
                        children =
                        [dcc.Dropdown(
                            id = 'experiment_dropdown',
                            options = [{'label': x, 'value': x} for x in exp_options],
                            multi = True
                        )]
                    ),
                    html.Hr(),
                    html.H5(
                        'Download images as:'
                    ),
                    dcc.RadioItems(
                        id='download-format-options',
                        options = [
                            {'label': 'png', 'value': 'png'},
                            {'label': 'svg', 'value': 'svg'},
                            {'label': 'jpeg', 'value': 'jpeg'},
                            {'label': 'webp', 'value': 'webp'},
                        ],
                        value = 'png',
                        labelStyle = {'display': 'inline-block', 'text-align': 'center'},
                        style = {'width': '100%'}

                    ),
                    html.P(
                        id = 'info-p',
                        children = 'Note that the button may still read "png" due to a plotly bug.',
                        style = {
                            'padding-top': '2px',
                            'color': '#00000066',
                            'font-style': 'italic'
                        }
                    ),
                    dcc.Checklist(
                        options=[
                            {'label': 'Overlay preparative trace on analytic graphs', 'value': 'overlay'}
                        ],
                        id = 'fplc-overlay'
                    ),
                    # HPLC options
                    html.Div(
                        id = 'hplc-options-sidebar',
                        children = [
                            html.Hr(),
                            dcc.Download(id = 'download-hplc-dataframe'),
                            html.H5(
                                style = {'paddingTop': '10px', 'textAlign': 'center'},
                                children = 'Analytic Chromatography Options'
                            ),
                            dcc.RadioItems(
                                id = 'x-ax-radios',
                                options=[
                                    {'label': 'Volume', 'value': 'mL'},
                                    {'label': 'Time', 'value': 'Time'}
                                ],
                                value='mL',
                                labelStyle = {'display': 'inline-block', 'text-align': 'center'},
                                style = {'width': '100%'}
                            ),
                            html.Br(),
                            html.Button(
                                'Renormalize Analytic',
                                id = 'renorm-hplc',
                                style = {'width': '100%'}
                            ),
                            html.Button(
                                'Reset normalization',
                                id = 'reset-norm',
                                style = {'width': '100%'}
                            ),
                            html.Button(
                                'Reset Analytic',
                                id = 'reset-hplc',
                                style = {'width': '100%'}
                            ),
                            html.Div(
                                style={'height': '1em'}
                            ),
                            html.Button(
                                'Download Long CSV',
                                id='download-hplc-long',
                                style = {'width': '100%'}
                            ),
                            html.Button(
                                'Download Wide CSV',
                                id='download-hplc-wide',
                                style = {'width': '100%'}
                            )
                        ]
                    ),
                    html.Hr(),
                    html.Div(
                        id='fplc-options-sidebar',
                        children = [
                            html.H5(
                                style = {'paddingTop': '10px', 'textAlign': 'center'},
                                children = 'Preparative Chromatography Options'
                            ),
                            html.Button(
                                'Download Prep. CSV',
                                id = 'download-fplc',
                                style = {'width': '100%'}
                            )
                        ]
                    )
                ]
            ),
            html.Div(
                className = 'graphs',
                children = html.Div(id = 'main_graphs')
            )
        ]
    )

app.layout = serve_layout

# Update graph experiment title

@app.callback(
    dash.dependencies.Output('output-container', 'children'),
    [dash.dependencies.Input('root-location', 'pathname')])
def update_output(pathname):
    experiment_name = pathname.replace(url_basename, '').replace('+', ' and ').replace('%20', ' ')
    return f'{experiment_name}'

# Make URL pathname the experiment name(s)

@app.callback(
    dash.dependencies.Output('root-location', 'pathname'),
    [dash.dependencies.Input('experiment_dropdown', 'value')]
)
def update_url(value):
    if value is not None:
        return '+'.join(value)

# load graphs, normalize experiment, update query string

@app.callback(
    [
        dash.dependencies.Output('main_graphs', 'children'),
        dash.dependencies.Output('hplc-options-sidebar', 'hidden'),
        dash.dependencies.Output('fplc-options-sidebar', 'hidden'),
    ],
    [
        dash.dependencies.Input('root-location', 'pathname'),
        dash.dependencies.Input('root-location', 'search'),
        dash.dependencies.Input('x-ax-radios', 'value'),
        dash.dependencies.Input('renorm-hplc', 'n_clicks'),
        dash.dependencies.Input('reset-norm', 'n_clicks'),
        dash.dependencies.Input('reset-hplc', 'n_clicks'),
        dash.dependencies.Input('download-format-options', 'value'),
        dash.dependencies.Input('fplc-overlay', 'value')
    ]
)
def create_graphs(
    pathname, search_string, radio_value,
    renorm, reset_norm, reset, 
    format_val, overlay_val):
    changed = [p['prop_id'] for p in dash.callback_context.triggered][0]

    if changed == 'root-location.search' or changed is None:
        raise dash.exceptions.PreventUpdate

    if pathname != '':
        
        experiment_name_list = exp_list_from_pathname(pathname)
        
        norm_range, view_range = parse_query(search_string)

        if changed == 'renorm-hplc.n_clicks':
            norm_range = view_range

        exp = get_experiments(experiment_name_list)

        # don't overlay if there is no HPLC data!
        overlay = overlay_val and exp.hplc is not None

        if norm_range is not None:
            exp.renormalize_hplc(norm_range, False)
        
        return (
            get_plotly(exp, view_range, radio_value, format_val, overlay),
            exp.hplc is None,
            exp.fplc is None and not overlay
        )

@app.callback(
    dash.dependencies.Output('root-location', 'search'),
    [
        dash.dependencies.Input('data-Signal', 'relayoutData'),
        dash.dependencies.Input('root-location', 'search'),
        dash.dependencies.Input('renorm-hplc', 'n_clicks'),
        dash.dependencies.Input('reset-norm', 'n_clicks'),
        dash.dependencies.Input('reset-hplc', 'n_clicks')
    ]
)
def refresh_xrange(relayout_data, search_string, renorm, reset_norm, reset):
    changed = [p['prop_id'] for p in dash.callback_context.triggered][0]

    norm_range, view_range = parse_query(search_string)

    if changed == 'reset-hplc.n_clicks' or changed == 'reset-norm.n_clicks':
        if changed == 'reset-norm.n_clicks' and view_range:
            return f'?view-range={view_range[0]}-{view_range[1]}'
        else:
            return ''

    if relayout_data == None or changed == 'root-location.search':
        raise dash.exceptions.PreventUpdate    

    try:
        data = [relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']]
    except KeyError:
        try:
            if relayout_data['xaxis2.autorange']:
                data = None
        except KeyError:
            raise dash.exceptions.PreventUpdate

    norm_range, view_range = parse_query(search_string)

    new_q_string = '?'

    if changed == 'renorm-hplc.n_clicks':
        new_q_string = new_q_string + f'norm-range={view_range[0]}-{view_range[1]}&'
    elif norm_range is not None:
        new_q_string = new_q_string + f'norm-range={norm_range[0]}-{norm_range[1]}&'

    if data is not None:
        new_q_string = new_q_string + f'view-range={data[0]}-{data[1]}'

    return new_q_string

@app.callback(
    dash.dependencies.Output('download-hplc-dataframe', 'data'),
    [
        dash.dependencies.Input('download-hplc-long', 'n_clicks'),
        dash.dependencies.Input('download-hplc-wide', 'n_clicks'),
        dash.dependencies.Input('download-fplc', 'n_clicks'),
        dash.dependencies.Input('root-location', 'pathname')
    ],
    prevent_initial_call = True
)
def download_csv(hplc_l, hplc_w, fplc, pathname):
    changed = [p['prop_id'] for p in dash.callback_context.triggered][0]

    if changed is None or changed == 'root-location.pathname':
        raise dash.exceptions.PreventUpdate
    else:
        exp_list = exp_list_from_pathname(pathname)
        exp = get_experiments(exp_list)

    if changed == 'download-hplc-long.n_clicks':
        if exp.hplc is not None:
            return dcc.send_data_frame(exp.hplc.to_csv, 'hplc-long.csv', index = False)
    elif changed == 'download-hplc-wide.n_clicks':
        if exp.hplc is not None:
            return dcc.send_data_frame(exp.wide.to_csv, 'hplc-wide.csv', index = False)
    elif changed == 'download-fplc.n_clicks':
        if exp.fplc is not None:
            return dcc.send_data_frame(exp.fplc.to_csv, 'fplc.csv', index = False)

if __name__ == '__main__':
    app.run_server(port = '8080')