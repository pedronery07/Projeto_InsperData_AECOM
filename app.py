import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import dash_leaflet as dl
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
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
    # Tipo de impacto
    if 'tipo_impacto' in df_base.columns:
        df_base['tipo_impacto'] = df_base['tipo_impacto'].fillna('Não Especificado')
    else:
        df_base['tipo_impacto'] = 'Não Especificado'
    # UF
    if 'uf' in df_base.columns:
        df_base['uf'] = df_base['uf'].fillna('Não Informado').astype(str)
    else:
        df_base['uf'] = 'Não Informado'
    # Filtra apenas registros com lat/lon válidos
    df_mapeavel = df_base.dropna(subset=['latitude', 'longitude']).copy()
    print(f"Número de registros mapeáveis: {len(df_mapeavel)}")
except Exception as e:
    print(f"ERRO ao carregar dados: {e}. Dashboard iniciará com dados vazios.")
    df_base = pd.DataFrame()
    df_mapeavel = pd.DataFrame(columns=[
        'latitude','longitude','tipo_impacto','valor_multa_numerico',
        'numero_processo','municipio','uf','descricao_impacto'
    ])

# Opções de filtro
tipos_impacto_opcoes = [ {'label': t,'value': t} for t in sorted(df_mapeavel['tipo_impacto'].unique()) ]
ufs_opcoes = [ {'label': u,'value': u} for u in sorted(df_mapeavel['uf'].unique()) ]

# Slider de valor multa
min_multa = float(df_mapeavel['valor_multa_numerico'].min()) if not df_mapeavel.empty else 0
max_multa = float(df_mapeavel['valor_multa_numerico'].max()) if not df_mapeavel.empty else 1000000
if min_multa >= max_multa:
    max_multa = min_multa + 100
step_multa = (max_multa - min_multa) / 100 if max_multa > min_multa else 1

# Mapa de cores por tipo
all_tipos = sorted(df_mapeavel['tipo_impacto'].unique())
colors = px.colors.qualitative.Plotly * (
    len(all_tipos)//len(px.colors.qualitative.Plotly) + 1
)
color_map = { t: colors[i] for i, t in enumerate(all_tipos) }

# Colunas da tabela
colunas_tabela = [
    {"name": "Processo", "id": "numero_processo"},
    {"name": "Município", "id": "municipio"},
    {"name": "UF", "id": "uf"},
    {"name": "Tipo de Impacto", "id": "tipo_impacto"},
    {"name": "Valor Multa (R$)", "id": "valor_multa_numerico_formatado", "type": "text"},
    {"name": "Descrição", "id": "descricao_impacto"}
]

# Helper para formatar moeda

def format_brl_currency(value):
    if pd.isna(value):
        return ""
    tmp = f"{value:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
    return f"R$ {tmp}"

# --- DASH SETUP ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Layout
app.layout = html.Div([
    # Cabeçalho
    html.Div([
        html.Img(src=app.get_asset_url('aecom.png'), style={'height':'50px','marginRight':'20px'}),
        html.H1("Valoração de Danos Ambientais", style={'textAlign':'center','color':'#212529','margin':0}),
        html.Img(src=app.get_asset_url('data.png'), style={'height':'50px','marginLeft':'20px'})
    ], style={'display':'flex','justifyContent':'center','alignItems':'center','marginBottom':'20px'}),

    # Filtros + Mapa/Gráfico
    html.Div([
        # Sidebar
        html.Div([
            html.H4("Filtros", style={'marginTop':0}),
            dcc.Dropdown(id='dropdown-tipo-impacto', options=tipos_impacto_opcoes, value=[], multi=True, placeholder="Selecione o(s) tipo(s) de impacto"),
            html.Br(),
            dcc.Dropdown(id='dropdown-uf', options=ufs_opcoes, value=[], multi=True, placeholder="Selecione o(s) estado(s)"),
            html.Br(),
            dcc.RangeSlider(
                id='rangeslider-valor-multa',
                min=min_multa, max=max_multa, step=step_multa,
                value=[min_multa, max_multa], tooltip={'placement':'bottom','always_visible':True}
            ),
            html.Br(),
            html.Button('Limpar Filtros', id='btn-limpar-filtros', n_clicks=0,
                        style={'marginTop':'10px','width':'100%','backgroundColor':'#007bff','color':'white','border':'none','padding':'10px','borderRadius':'5px','cursor':'pointer'}),
            html.Hr(),
            html.Div(id='total-registros-carregados', style={'marginTop':'15px'}),
            html.Hr(),
            html.Div(id='custom-legend-container')
        ], className='sidebar', style={'width':'23%','padding':'20px','boxSizing':'border-box','float':'left','backgroundColor':'#F8F9FA','borderRadius':'5px'}),

        # Container do Mapa e Gráfico
        html.Div([
            html.Div([
                dl.Map(
                    id='mapa-danos-ambientais',
                    center=[-14.2350, -51.9253],
                    zoom=4,
                    style={'width':'100%','height':'75vh'},
                    children=[
                        dl.TileLayer(),
                        dl.ScaleControl(position='bottomright'),
                        dl.LayerGroup(id='markers-layer')
                    ]
                ),
                # seta norte
                html.Img(src=app.get_asset_url('north_arrow.png'),
                         style={'position':'absolute','bottom':'60px','right':'10px','width':'50px','zIndex':'1000'})
            ], style={'position':'relative'}),
            html.Div([
                dcc.Graph(id='bar-chart-avg-multa', style={'height':'40vh','marginTop':'20px'})
            ])
        ], className='map-and-chart-container', style={'width':'75%','padding':'10px','boxSizing':'border-box','float':'right'})
    ], style={'display':'flex','flexDirection':'row','marginBottom':'20px'}),

    # Resumo e Tabela
    html.Div([
        html.H4("Resumo e Dados Filtrados", style={'textAlign':'center'}),
        html.Div(id='resumo-resultados', style={'padding':'10px','textAlign':'center','fontWeight':'bold','backgroundColor':'#E0F2F7','borderRadius':'5px','marginBottom':'10px'}),
        dash_table.DataTable(
            id='tabela-dados-filtrados',
            columns=colunas_tabela,
            data=[],
            page_size=10,
            filter_action="native", sort_action="native",
            export_format="xlsx", export_headers="display",
            style_cell={'textAlign':'center','fontFamily':'Arial, sans-serif','minWidth':'100px','width':'150px','maxWidth':'300px','overflow':'hidden','textOverflow':'ellipsis'},
            style_header={'backgroundColor':'#E9ECEF','fontWeight':'bold'},
            style_data={'whiteSpace':'normal','height':'auto'}
        )
    ], style={'padding':'20px','clear':'both'})
], style={'fontFamily':'Arial, sans-serif','margin':'auto','maxWidth':'1600px','backgroundColor':'#FFFFFF'})

# --- CALLBACKS ---
# Limpar filtros
@app.callback(
    [Output('dropdown-tipo-impacto','value'), Output('rangeslider-valor-multa','value'), Output('dropdown-uf','value')],
    [Input('btn-limpar-filtros','n_clicks')], prevent_initial_call=True
)
def limpar_filtros(n):
    return [], [min_multa, max_multa], []

# Legenda customizada
@app.callback(
    Output('custom-legend-container','children'),
    [Input('dropdown-tipo-impacto','value'), Input('rangeslider-valor-multa','value'), Input('dropdown-uf','value')]
)
def update_custom_legend(selected_tipos, selected_valores, selected_ufs):
    if df_mapeavel.empty:
        return html.Details([html.Summary(html.Strong("Legenda do Mapa (clique para expandir/minimizar)")),
                              html.Div(html.P("Nenhum dado para exibir."), style={'padding':'10px'})],
                            open=True, style={'border':'1px solid #ddd','borderRadius':'5px','padding':'10px','marginTop':'10px'})
    dff = df_mapeavel.copy()
    if selected_tipos: dff = dff[dff['tipo_impacto'].isin(selected_tipos)]
    if selected_valores:
        mn, mx = selected_valores
        dff = dff[(dff['valor_multa_numerico']>=mn)&(dff['valor_multa_numerico']<=mx)]
    if selected_ufs: dff = dff[dff['uf'].isin(selected_ufs)]
    items=[]
    if not dff.empty:
        for t in sorted(dff['tipo_impacto'].unique()):
            items.append(html.Li([
                html.Span(style={'display':'inline-block','width':'12px','height':'12px','borderRadius':'50%','backgroundColor':color_map.get(t),'marginRight':'5px'}),
                html.Span(t)
            ], style={'marginBottom':'5px'}))
    else:
        items.append(html.Li("Nenhum tipo de impacto encontrado."))
    return html.Details([html.Summary(html.Strong("Legenda do Mapa (clique para expandir/minimizar)")),
                         html.Div(html.Ul(items, style={'listStyleType':'none','paddingLeft':'0','margin':'0'}), style={'maxHeight':'40vh','overflowY':'auto','padding':'10px'})],
                        open=True, style={'border':'1px solid #CED4DA','borderRadius':'5px','padding':'10px','marginTop':'10px'})

# Atualiza marcadores no mapa
@app.callback(
    Output('markers-layer','children'),
    [Input('dropdown-tipo-impacto','value'), Input('rangeslider-valor-multa','value'), Input('dropdown-uf','value')]
)
def update_markers(selected_tipos, selected_valores, selected_ufs):
    dff = df_mapeavel.copy()
    if selected_tipos: dff = dff[dff['tipo_impacto'].isin(selected_tipos)]
    if selected_valores:
        mn, mx = selected_valores
        dff = dff[(dff['valor_multa_numerico']>=mn)&(dff['valor_multa_numerico']<=mx)]
    if selected_ufs: dff = dff[dff['uf'].isin(selected_ufs)]
    markers=[]
    for _, row in dff.iterrows():
        markers.append(
            dl.CircleMarker(
                center=[row.latitude, row.longitude],
                radius=8,
                color=color_map.get(row.tipo_impacto,'#666'),
                fill=True, fillOpacity=0.7,
                children=[
                    dl.Tooltip(f"{row.numero_processo}"),
                    dl.Popup(html.Div([
                        html.B(row.tipo_impacto),
                        html.P(f"Município: {row.municipio}/{row.uf}"),
                        html.P(f"Valor: R$ {row.valor_multa_numerico:,.2f}"),
                        html.P(row.descricao_impacto)
                    ]))
                ]
            )
        )
    return markers

# Atualiza gráfico, texto e tabela
@app.callback(
    [Output('bar-chart-avg-multa','figure'), Output('resumo-resultados','children'),
     Output('tabela-dados-filtrados','data'), Output('total-registros-carregados','children')],
    [Input('dropdown-tipo-impacto','value'), Input('rangeslider-valor-multa','value'), Input('dropdown-uf','value')]
)
def update_dashboard(selected_tipos, selected_valores, selected_ufs):
    total_text = f"Total de registros no arquivo original: {len(df_base)}"
    if df_mapeavel.empty:
        return go.Figure(), "Nenhum dado carregado para exibir.", [], total_text
    dff = df_mapeavel.copy()
    if selected_tipos: dff = dff[dff['tipo_impacto'].isin(selected_tipos)]
    if selected_valores:
        mn, mx = selected_valores
        dff = dff[(dff['valor_multa_numerico']>=mn)&(dff['valor_multa_numerico']<=mx)]
    if selected_ufs: dff = dff[dff['uf'].isin(selected_ufs)]
    total_text = f"Registros mapeáveis carregados: {len(df_mapeavel)} (de {len(df_base)} no total)"
    if dff.empty:
        empty_fig = go.Figure().update_layout(
            title="Valor Médio da Multa por Tipo de Impacto",
            xaxis_title="Tipo de Impacto", yaxis_title="Valor Médio da Multa (R$)"
        )
        return empty_fig, "Nenhum resultado para os filtros selecionados.", [], total_text
    # formata valores e tabela
    dff['valor_multa_numerico_formatado'] = dff['valor_multa_numerico'].apply(format_brl_currency)
    # gráfico de barras
    df_avg = dff.groupby('tipo_impacto')['valor_multa_numerico'].mean().reset_index()
    df_avg.columns = ['Tipo de Impacto','Valor Médio da Multa']
    df_avg = df_avg.sort_values('Valor Médio da Multa', ascending=False)
    fig_bar = px.bar(
        df_avg, x='Tipo de Impacto', y='Valor Médio da Multa',
        title='Valor Médio da Multa por Tipo de Impacto',
        color='Tipo de Impacto', color_discrete_map=color_map,
        hover_data={'Valor Médio da Multa': ':.2f'}
    )
    fig_bar.update_layout(xaxis_title="Tipo de Impacto", yaxis_title="Valor Médio da Multa (R$)", showlegend=False)
    fig_bar.update_yaxes(tickprefix='R$ ')
    # texto resumo
    count = len(dff)
    total_m = dff['valor_multa_numerico'].sum()
    mean_m  = dff['valor_multa_numerico'].mean()
    resumo = f"Resultados para os filtros: {count} caso(s) encontrado(s). Valor Total das Multas: R$ {total_m:,.2f}. Média da Multa: R$ {mean_m:,.2f}."
    table_data = dff[['numero_processo','municipio','uf','tipo_impacto','valor_multa_numerico_formatado','descricao_impacto']].to_dict('records')
    return fig_bar, resumo, table_data, total_text

# --- RODAR APP ---
if __name__ == '__main__':
    assets_folder = os.path.join(os.path.dirname(__file__), 'assets')
    os.makedirs(assets_folder, exist_ok=True)
    for asset in ['data.png','aecom.png','north_arrow.png']:
        path = os.path.join(assets_folder, asset)
        if not os.path.exists(path):
            print(f"AVISO: '{asset}' não encontrado em {assets_folder}.")
    if df_base.empty:
        print("ERRO: Dados não encontrados. Execute geocodificação primeiro.")
    else:
        print("Iniciando servidor Dash em http://127.0.0.1:8050/")
        app.run(debug=True)
