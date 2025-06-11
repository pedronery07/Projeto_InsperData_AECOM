import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import dash_leaflet as dl
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import os

# --- CARREGAMENTO E PRÉ-PROCESSAMENTO DOS DADOS ---
geocoded_excel_path = 'docs/results_geocoded.xlsx'
print(f"Carregando dados geocodificados de: {geocoded_excel_path}")
try:
    df_base = pd.read_excel(geocoded_excel_path)
    print(f"Dados carregados. {len(df_base)} linhas encontradas.")
    # Valor multa numérico
    if 'valor_multa' in df_base.columns:
        df_base['valor_multa_numerico'] = pd.to_numeric(
            df_base['valor_multa'].astype(str).str.replace(',', '.'),
            errors='coerce'
        ).fillna(0)
    else:
        df_base['valor_multa_numerico'] = 0
    # Moeda
    if 'moeda' in df_base.columns:
        df_base['moeda'] = df_base['moeda'].fillna('Desconhecida')
    else:
        df_base['moeda'] = 'Desconhecida'
    # Tipo de impacto detalhado e geral
    df_base['tipo_impacto'] = df_base.get('tipo_impacto', 'Não Especificado').fillna('Não Especificado')
    df_base['tipo_impacto_geral'] = df_base.get('tipo_impacto_geral', 'Não Especificado').fillna('Não Especificado')
    # UF
    df_base['uf'] = df_base.get('uf', 'Não Informado').fillna('Não Informado').astype(str)
    # Filtra registros mapeáveis
    df_mapeavel = df_base.dropna(subset=['latitude', 'longitude']).copy()
    print(f"Número de registros mapeáveis: {len(df_mapeavel)}")
except Exception as e:
    print(f"ERRO ao carregar dados: {e}. Dashboard iniciará com dados vazios.")
    df_base = pd.DataFrame()
    df_mapeavel = pd.DataFrame(columns=[
        'latitude','longitude','tipo_impacto','tipo_impacto_geral','valor_multa_numerico','moeda',
        'numero_processo','municipio','uf','descricao_impacto'
    ])

# --- PARÂMETROS DE FILTRO ---
# Filtros de impacto geral
tipos_gerais_opcoes = [
    {'label': t, 'value': t}
    for t in sorted(df_mapeavel['tipo_impacto_geral'].unique())] if not df_mapeavel.empty else []
# Filtros de UF
ufs_opcoes = [ {'label': u,'value': u} for u in sorted(df_mapeavel['uf'].unique()) ]
# Filtros de moeda
moeda_opcoes = [ {'label': m,'value': m} for m in sorted(df_mapeavel['moeda'].unique()) ]

# Slider log10 para valor da multa em R$
vals = df_mapeavel[(df_mapeavel['moeda']=='R$') & (df_mapeavel['valor_multa_numerico']>0)]['valor_multa_numerico']
min_log = int(np.floor(np.log10(vals.min()))) if not vals.empty else 0
max_log = int(np.ceil(np.log10(vals.max())))  if not vals.empty else 6

# Cores por impacto geral
cores = px.colors.qualitative.Plotly * (
    len(tipos_gerais_opcoes)//len(px.colors.qualitative.Plotly)+1
)
color_map = { t: cores[i] for i, t in enumerate(sorted(df_mapeavel['tipo_impacto_geral'].unique())) }

# Colunas da tabela
colunas_tabela = [
    {"name":"Processo","id":"numero_processo"},
    {"name":"Municipio","id":"municipio"},
    {"name":"UF","id":"uf"},
    {"name":"Impacto Detalhado","id":"tipo_impacto"},
    {"name":"Impacto Geral","id":"tipo_impacto_geral"},
    {"name":"Moeda","id":"moeda"},
    {"name":"Valor Multa (R$)","id":"valor_multa_numerico_formatado","type":"text"},
    {"name":"Descrição","id":"descricao_impacto"}
]

# Helper formata moeda
def format_currency(value, currency):
    if pd.isna(value) or value == 0:
        return ""
    tmp = f"{value:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    return f"{currency} {tmp}"

# --- DASH APP ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.layout = html.Div([
    # Cabeçalho
    html.Div([
        html.Img(src=app.get_asset_url('aecom.png'), style={'height':'50px','marginRight':'20px'}),
        html.H1("Valoração de Danos Ambientais", style={'textAlign':'center','margin':0}),
        html.Img(src=app.get_asset_url('data.png'), style={'height':'50px','marginLeft':'20px'})
    ], style={'display':'flex','justifyContent':'center','alignItems':'center','marginBottom':'20px'}),

    # Sidebar de filtros
    html.Div([
        html.H4("Filtros", style={'marginTop':0}),
        html.Label("Impacto Geral:"),
        dcc.Dropdown(id='dropdown-geral', options=tipos_gerais_opcoes,value=[],multi=True),
        html.Br(),
        html.Label("UF:"),
        dcc.Dropdown(id='dropdown-uf', options=ufs_opcoes, value=[], multi=True),
        html.Br(),
        html.Label("Moeda:"),
        dcc.Dropdown(id='dropdown-moeda', options=moeda_opcoes, value=['R$'], multi=True),
        html.Br(),
        dcc.Checklist(
            id='check-hide-zero',
            options=[{'label':'Ocultar multas = 0','value':'hide_zero'}],
            value=[],
            labelStyle={'display':'inline-block','marginRight':'10px'}
        ),
        html.Hr(),
        dcc.Graph(id='hist-multa-log', config={'displayModeBar':False}, style={'height':'120px'}),
        dcc.RangeSlider(
            id='rangeslider-log', min=min_log, max=max_log, step=1,
            value=[min_log, max_log],
            marks={i:f"10^{i}" for i in range(min_log, max_log+1)},
            tooltip={'placement':'bottom','always_visible':False}
        ),
        html.Div(id='display-range-log', style={'textAlign':'center','marginTop':'5px'}),
        html.Br(),
        html.Button('Limpar Filtros', id='btn-limpar', n_clicks=0, style={'width':'100%'}),
        html.Hr(),
        html.Div(id='custom-legend')
    ], style={'width':'25%','padding':'20px','float':'left','backgroundColor':'#F8F9FA'}),

    # Mapa e Gráfico
    html.Div([
        html.Div([
            dl.Map(
                id='mapa', center=[-14.2350,-51.9253], zoom=4,
                style={'width':'100%','height':'70vh'}, children=[
                    dl.TileLayer(), dl.ScaleControl(position='bottomright'),
                    dl.LayerGroup(id='markers')
                ]
            ),
            html.Img(src=app.get_asset_url('north_arrow.png'), style={'position':'absolute','bottom':'60px','right':'10px','width':'50px', 'zIndex': 1000})
        ], style={'position':'relative'}),
        html.Div([dcc.Graph(id='bar-chart', style={'height':'35vh','marginTop':'20px'})])
    ], style={'width':'73%','float':'right'}),

    # Resumo e Tabela
    html.Div([
        html.H4("Resumo e Dados Filtrados", style={'textAlign':'center'}),
        html.Div(id='resumo', style={'padding':'10px','fontWeight':'bold','backgroundColor':'#E0F2F7'}),
        dash_table.DataTable(
            id='tabela', columns=colunas_tabela, data=[], page_size=10,
            filter_action='native', sort_action='native',
            export_format='xlsx', export_headers='display',
            style_cell={'textAlign':'center'}, style_header={'fontWeight':'bold'}
        )
    ], style={'clear':'both','padding':'20px'})
])

# --- CALLBACKS ---
@app.callback(
    [Output('dropdown-geral','value'), Output('dropdown-uf','value'),
     Output('dropdown-moeda','value'), Output('check-hide-zero','value'),
     Output('rangeslider-log','value')],
    Input('btn-limpar','n_clicks'), prevent_initial_call=True
)
def limpar(n):
    return [], [], ['R$'], [], [min_log, max_log]

@app.callback(
    Output('display-range-log','children'),
    Input('rangeslider-log','value')
)
def show_range(r):
    lo, hi = r
    return f"Faixa: R$ {10**lo:,.0f} ⇥ R$ {10**hi:,.0f}"

@app.callback(
    Output('hist-multa-log','figure'),
    [Input('dropdown-moeda','value'), Input('check-hide-zero','value')]
)
def update_hist(moedas, hide_zero):
    dfh = df_mapeavel.copy()
    if moedas: dfh = dfh[dfh['moeda'].isin(moedas)]
    if 'hide_zero' in hide_zero: dfh = dfh[dfh['valor_multa_numerico']>0]
    # hist de log
    vals_h = np.log10(dfh[dfh['moeda']=='R$']['valor_multa_numerico']+1)
    fig = px.histogram(vals_h, nbins=max_log-min_log+1, range_x=(min_log,max_log))
    fig.update_layout(margin={'l':0,'r':0,'t':0,'b':0}, xaxis_title='log10(Valor+1)')
    return fig

@app.callback(
    Output('custom-legend','children'),
    [Input('dropdown-geral','value'), Input('dropdown-moeda','value'),
     Input('check-hide-zero','value'), Input('rangeslider-log','value')]
)
def update_legend(sel_g, moedas, hide_zero, range_log):
    if df_mapeavel.empty:
        return html.Div("Sem dados para legenda.")
    dff = df_mapeavel.copy()
    if sel_g: dff = dff[dff['tipo_impacto_geral'].isin(sel_g)]
    if moedas: dff = dff[dff['moeda'].isin(moedas)]
    if 'hide_zero' in hide_zero: dff = dff[dff['valor_multa_numerico']>0]
    lo, hi = range_log; dff = dff[(dff['valor_multa_numerico']>=10**lo)&(dff['valor_multa_numerico']<=10**hi)]
    items = []
    for g in sorted(dff['tipo_impacto_geral'].unique()):
        items.append(html.Li([
            html.Span(style={'backgroundColor':color_map[g],'display':'inline-block','width':'12px','height':'12px','borderRadius':'50%','marginRight':'5px'}),
            html.Span(g)
        ]))
    return html.Details([html.Summary("Legenda (Impacto Geral)"), html.Ul(items, style={'listStyle':'none'})], open=True)

@app.callback(
    Output('markers','children'),
    [Input('dropdown-geral','value'), Input('dropdown-uf','value'),
     Input('dropdown-moeda','value'), Input('check-hide-zero','value'),
     Input('rangeslider-log','value')]
)
def update_markers(sel_g, sel_uf, moedas, hide_zero, rlog):
    dff = df_mapeavel.copy()
    if sel_g: dff = dff[dff['tipo_impacto_geral'].isin(sel_g)]
    if sel_uf: dff = dff[dff['uf'].isin(sel_uf)]
    if moedas: dff = dff[dff['moeda'].isin(moedas)]
    if 'hide_zero' in hide_zero: dff = dff[dff['valor_multa_numerico']>0]
    lo, hi = rlog; dff = dff[(dff['valor_multa_numerico']>=10**lo)&(dff['valor_multa_numerico']<=10**hi)]
    markers = []
    for _, row in dff.iterrows():
        markers.append(dl.CircleMarker(
            center=[row.latitude,row.longitude], radius=8,
            color=color_map[row.tipo_impacto_geral], fill=True, fillOpacity=0.7,
            children=[
                dl.Tooltip(f"{row.numero_processo} | Geral: {row.tipo_impacto_geral}"),
                dl.Popup(html.Div([
                    html.B(f"Impacto Geral: {row.tipo_impacto_geral}"),
                    html.P(f"Det.: {row.tipo_impacto}"),
                    html.P(f"Valor: {format_currency(row.valor_multa_numerico, row.moeda)}"),
                    html.P(f"Moeda: {row.moeda}"),
                    html.P(row.descricao_impacto)
                ]))
            ]
        ))
    return markers

@app.callback(
    [Output('bar-chart','figure'), Output('resumo','children'), Output('tabela','data')],
    [Input('dropdown-geral','value'), Input('dropdown-uf','value'),
     Input('dropdown-moeda','value'), Input('check-hide-zero','value'),
     Input('rangeslider-log','value')]
)
def update_dashboard(sel_g, sel_uf, moedas, hide_zero, rlog):
    dff = df_mapeavel.copy()
    if sel_g: dff = dff[dff['tipo_impacto_geral'].isin(sel_g)]
    if sel_uf: dff = dff[dff['uf'].isin(sel_uf)]
    if moedas: dff = dff[dff['moeda'].isin(moedas)]
    if 'hide_zero' in hide_zero: dff = dff[dff['valor_multa_numerico']>0]
    lo, hi = rlog; dff = dff[(dff['valor_multa_numerico']>=10**lo)&(dff['valor_multa_numerico']<=10**hi)]
    # gráfico barras por impacto geral
    df_avg = dff.groupby('tipo_impacto_geral')['valor_multa_numerico'].mean().reset_index()
    fig = px.bar(df_avg, x='tipo_impacto_geral', y='valor_multa_numerico', color='tipo_impacto_geral', color_discrete_map=color_map)
    fig.update_layout(title='Média da Multa por Impacto Geral', xaxis_title='', yaxis_title='R$ ', showlegend=False)
    # resumo texto
    total = len(dff)
    soma = dff['valor_multa_numerico'].sum()
    media = dff['valor_multa_numerico'].mean() if total>0 else 0
    resumo = f"{total} casos. Soma: R$ {soma:,.2f}. Média: R$ {media:,.2f}."
    # tabela
    dff['valor_multa_numerico_formatado'] = dff.apply(
        lambda row: format_currency(row['valor_multa_numerico'], row['moeda']), axis=1
    )
    data = dff[['numero_processo','municipio','uf','tipo_impacto','tipo_impacto_geral','moeda','valor_multa_numerico_formatado','descricao_impacto']].to_dict('records')
    return fig, resumo, data

# --- RUN ---
if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(__file__), 'assets'), exist_ok=True)
    app.run(debug=True)
