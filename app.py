# app_dashboard.py

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State # State para pegar valores atuais
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os

# --- CARREGAMENTO DOS DADOS PRÉ-GECODIFICADOS ---
geocoded_excel_path = 'docs/results_geocoded.xlsx'

print(f"Carregando dados geocodificados de: {geocoded_excel_path}")
df_base = pd.DataFrame() # Inicializar como DataFrame vazio
try:
    df_base = pd.read_excel(geocoded_excel_path)
    print(f"Dados carregados. {len(df_base)} linhas encontradas.")
except FileNotFoundError:
    print(f"ERRO CRÍTICO: O arquivo de dados geocodificados '{geocoded_excel_path}' não foi encontrado.")
    print("Por favor, execute o script de geocodificação primeiro (ex: geocode_data.py).")
except Exception as e:
    print(f"ERRO ao carregar o arquivo '{geocoded_excel_path}': {e}")

# --- PRÉ-PROCESSAMENTO NECESSÁRIO PARA O DASHBOARD ---
if not df_base.empty:
    # Garantir que a coluna 'valor_multa_numerico' exista e seja numérica
    if 'valor_multa' in df_base.columns:
        df_base['valor_multa_numerico'] = pd.to_numeric(df_base['valor_multa'], errors='coerce').fillna(0)
    else:
        print("AVISO: Coluna 'valor_multa' não encontrada. 'valor_multa_numerico' será criada com zeros.")
        df_base['valor_multa_numerico'] = 0

    # Garantir que 'tipo_impacto' não tenha NaNs
    if 'tipo_impacto' in df_base.columns:
        df_base['tipo_impacto'] = df_base['tipo_impacto'].fillna('Não Especificado')
    else:
        print("AVISO: Coluna 'tipo_impacto' não encontrada. Será criada com 'Não Especificado'.")
        df_base['tipo_impacto'] = 'Não Especificado'

    # Filtrar apenas linhas que têm coordenadas válidas para o mapa
    df_mapeavel = df_base.dropna(subset=['latitude', 'longitude']).copy() # Usar .copy()
    print(f"Número de registros mapeáveis após remover NaNs de lat/lon: {len(df_mapeavel)}")
else:
    # Se df_base estiver vazio, df_mapeavel também estará, mas com colunas para evitar erros
    df_mapeavel = pd.DataFrame(columns=[
        'latitude', 'longitude', 'tipo_impacto', 'valor_multa_numerico', 'numero_processo',
        'municipio', 'uf', 'descricao_impacto'
    ])
    if 'valor_multa_numerico' not in df_mapeavel.columns:
         df_mapeavel['valor_multa_numerico'] = pd.Series(dtype='float')
    if 'tipo_impacto' not in df_mapeavel.columns:
         df_mapeavel['tipo_impacto'] = pd.Series(dtype='object')
    print("AVISO: DataFrame base está vazio. O dashboard funcionará com dados limitados.")


# --- CONFIGURAÇÕES DO DASHBOARD ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Opções para dropdown e valores para slider
tipos_impacto_opcoes = []
if 'tipo_impacto' in df_mapeavel.columns and not df_mapeavel.empty:
    tipos_impacto_opcoes = [{'label': tipo, 'value': tipo} for tipo in sorted(df_mapeavel['tipo_impacto'].unique())]

# Valores min/max para o slider, tratando df vazio
min_multa_valor_inicial = 0
max_multa_valor_inicial = 1000000
if not df_mapeavel.empty and 'valor_multa_numerico' in df_mapeavel.columns:
    min_val_temp = df_mapeavel['valor_multa_numerico'].min()
    max_val_temp = df_mapeavel['valor_multa_numerico'].max()
    if pd.notna(min_val_temp):
        min_multa_valor_inicial = min_val_temp
    if pd.notna(max_val_temp):
        max_multa_valor_inicial = max_val_temp
    # Garantir que max > min
    if min_multa_valor_inicial >= max_multa_valor_inicial:
        max_multa_valor_inicial = min_multa_valor_inicial + 100 # Adiciona um range se todos os valores forem iguais ou min > max

slider_step = (max_multa_valor_inicial - min_multa_valor_inicial) / 100 if (max_multa_valor_inicial - min_multa_valor_inicial) > 0 else 1


# Colunas para a tabela de dados
colunas_tabela = [
    {"name": "Processo", "id": "numero_processo"},
    {"name": "Município", "id": "municipio"},
    {"name": "UF", "id": "uf"},
    {"name": "Tipo de Impacto", "id": "tipo_impacto"},
    {"name": "Valor Multa (R$)", "id": "valor_multa_numerico", "type": "numeric", "format": dash_table.Format.Format(precision=2, scheme=dash_table.Format.Scheme.fixed).group(True)},
    {"name": "Descrição", "id": "descricao_impacto"}
]

# --- LAYOUT DO DASHBOARD ---
app.layout = html.Div([
    html.H1("AECOM: Valoração de Danos Ambientais (Dash/Plotly)", style={'textAlign': 'center', 'marginBottom': '20px'}),

    # Linha contendo Sidebar e Mapa
    html.Div([
        # Sidebar com filtros
        html.Div([
            html.H4("Filtros", style={'marginTop': 0}),
            html.Label("Tipo de Impacto:"),
            dcc.Dropdown(
                id='dropdown-tipo-impacto',
                options=tipos_impacto_opcoes,
                value=[],
                multi=True,
                placeholder="Selecione o(s) tipo(s) de impacto"
            ),
            html.Br(),
            html.Label("Valor da Multa (R$):"),
            dcc.RangeSlider(
                id='rangeslider-valor-multa',
                min=min_multa_valor_inicial.round(2),
                max=max_multa_valor_inicial.round(2),
                step=slider_step,
                value=[min_multa_valor_inicial.round(2), max_multa_valor_inicial.round(2)],
                tooltip={"placement": "bottom", "always_visible": True},
                marks=None
            ),
            html.Br(),
            html.Button('Limpar Filtros', id='btn-limpar-filtros', n_clicks=0, style={'marginTop': '10px', 'width': '100%'}),
            html.Hr(),
            html.Div(id='total-registros-carregados', style={'marginTop': '15px'})

        ], className='sidebar', style={
            'width': '23%', 'padding': '20px', 'boxSizing': 'border-box',
            'float': 'left', 'backgroundColor': '#f9f9f9', 'borderRadius': '5px'
        }),

        # Container do Mapa
        html.Div([
            dcc.Graph(id='mapa-danos-ambientais', style={'height': '75vh'}) # Ajustar altura conforme necessário
        ], className='map-container', style={'width': '75%', 'padding': '10px', 'boxSizing': 'border-box', 'float': 'right'})

    ], style={'display': 'flex', 'flexDirection': 'row', 'marginBottom': '20px'}), # clear: 'both' não é mais necessário com flex

    # Resumo e Tabela de Dados
    html.Div([
        html.H4("Resumo e Dados Filtrados", style={'textAlign': 'center'}),
        html.Div(id='resumo-resultados', style={'padding': '10px', 'textAlign': 'center', 'fontWeight': 'bold'}),
        dash_table.DataTable(
            id='tabela-dados-filtrados',
            columns=colunas_tabela,
            data=[], # Inicialmente vazia
            page_size=10,
            style_cell={'textAlign': 'left', 'minWidth': '100px', 'width': '150px', 'maxWidth': '300px', 'overflow': 'hidden', 'textOverflow': 'ellipsis'},
            style_header={'backgroundColor': 'lightgrey', 'fontWeight': 'bold'},
            style_data={'whiteSpace': 'normal', 'height': 'auto'}, # Permite quebra de linha nas células
            filter_action="native", # Permite filtragem por coluna
            sort_action="native",   # Permite ordenação
            export_format="xlsx",   # Permite exportar para Excel
            export_headers="display"
        )
    ], style={'padding': '20px', 'clear': 'both'}) # clear: both aqui para garantir que fique abaixo

], style={'fontFamily': 'Arial, sans-serif', 'margin': 'auto', 'maxWidth': '1600px'})


# --- CALLBACKS DO DASHBOARD ---

# Callback para limpar filtros
@app.callback(
    [Output('dropdown-tipo-impacto', 'value'),
     Output('rangeslider-valor-multa', 'value')],
    [Input('btn-limpar-filtros', 'n_clicks')],
    prevent_initial_call=True # Não rodar na inicialização
)
def limpar_filtros(n_clicks):
    return [], [min_multa_valor_inicial, max_multa_valor_inicial]

# Callback principal para atualizar mapa, resumo e tabela
@app.callback(
    [Output('mapa-danos-ambientais', 'figure'),
     Output('resumo-resultados', 'children'),
     Output('tabela-dados-filtrados', 'data'),
     Output('total-registros-carregados', 'children')], # Novo output para total de registros
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value')]
)
def update_dashboard(selected_tipos_impacto, selected_valor_multa_range):
    if df_mapeavel.empty:
        fig = go.Figure(go.Scattermapbox(lat=[], lon=[]))
        fig.update_layout(mapbox_style="carto-positron", mapbox_zoom=2.5,
                          mapbox_center={"lat": -14.2350, "lon": -51.9253},
                          margin={"r":0,"t":0,"l":0,"b":0}, showlegend=False)
        resumo_texto = "Nenhum dado carregado para exibir."
        dados_tabela = []
        total_carregados_texto = f"Total de registros no arquivo original: {len(df_base)}"
        return fig, resumo_texto, dados_tabela, total_carregados_texto

    dff = df_mapeavel.copy() # Começa com todos os dados mapeáveis

    # Aplicar filtro de tipo de impacto
    if selected_tipos_impacto:
        dff = dff[dff['tipo_impacto'].isin(selected_tipos_impacto)]

    # Aplicar filtro de valor da multa
    if selected_valor_multa_range:
        min_val, max_val = selected_valor_multa_range
        dff = dff[(dff['valor_multa_numerico'] >= min_val) & (dff['valor_multa_numerico'] <= max_val)]

    # Texto para o total de registros carregados (não muda com filtros)
    total_carregados_texto = f"Registros mapeáveis carregados: {len(df_mapeavel)} (de {len(df_base)} no total)"

    # Gerar o mapa
    if dff.empty:
        fig = go.Figure(go.Scattermapbox(lat=[], lon=[]))
        fig.update_layout(
            mapbox_style="carto-positron",
            mapbox_zoom=2.5,
            mapbox_center={"lat": -14.2350, "lon": -51.9253},
            margin={"r":0,"t":0,"l":0,"b":0},
            showlegend=False # GARANTE QUE A LEGENDA NÃO APAREÇA
        )
        resumo_texto = "Nenhum resultado para os filtros selecionados."
        dados_tabela = []
    else:
        dff_plot = dff.copy()
        dff_plot.loc[:, 'marker_size'] = 10

        fig = px.scatter_map(
            dff_plot,
            lat="latitude",
            lon="longitude",
            color="tipo_impacto",
            size='marker_size',
            size_max=15,
            hover_name="numero_processo",
            hover_data={
                "municipio": True, "uf": True, "tipo_impacto": True,
                "valor_multa_numerico": ':.2f', "descricao_impacto": True,
                "latitude": False, "longitude": False, 'marker_size': False
            }
        )
        fig.update_layout(
            mapbox_style="carto-positron", # Ou "open-street-map"
            margin={"r":0,"t":0,"l":0,"b":0},
            showlegend=False # GARANTE QUE A LEGENDA NÃO APAREÇA
        )
        num_casos = len(dff)
        media_multa = dff['valor_multa_numerico'].mean() if num_casos > 0 else 0
        resumo_texto = f"Resultados para os filtros: {num_casos} caso(s) encontrado(s). Média da Multa (dos casos filtrados): R$ {media_multa:,.2f}"
        dados_tabela = dff[
            ["numero_processo", "municipio", "uf", "tipo_impacto", "valor_multa_numerico", "descricao_impacto"]
        ].to_dict('records')

    return fig, resumo_texto, dados_tabela, total_carregados_texto


# --- RODAR O APLICATIVO DASH ---
if __name__ == '__main__':
    if not os.path.exists(geocoded_excel_path) or df_base.empty:
         print("\n*************************************************************************************")
         print("ERRO: Arquivo de dados geocodificados não encontrado ou DataFrame base está vazio.")
         print(f"Verifique se '{geocoded_excel_path}' existe e contém dados.")
         print("Execute o script de geocodificação (ex: geocode_data.py) antes de rodar o dashboard.")
         print("*************************************************************************************")
    else:
        print("\nIniciando o servidor Dash...")
        print(f"Acesse o dashboard em: http://127.0.0.1:8050/")
        app.run(debug=True)