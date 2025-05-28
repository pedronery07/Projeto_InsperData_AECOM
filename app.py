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
        # Adicionei .astype(str).str.replace(',', '.') para lidar com vírgulas como separador decimal
        df_base['valor_multa_numerico'] = pd.to_numeric(df_base['valor_multa'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    else:
        print("AVISO: Coluna 'valor_multa' não encontrada. 'valor_multa_numerico' será criada com zeros.")
        df_base['valor_multa_numerico'] = 0

    # Garantir que 'tipo_impacto' não tenha NaNs
    if 'tipo_impacto' in df_base.columns:
        df_base['tipo_impacto'] = df_base['tipo_impacto'].fillna('Não Especificado')
    else:
        print("AVISO: Coluna 'tipo_impacto' não encontrada. Será criada com 'Não Especificado'.")
        df_base['tipo_impacto'] = 'Não Especificado'

    # Garantir que 'uf' não tenha NaNs e seja string
    if 'uf' in df_base.columns:
        df_base['uf'] = df_base['uf'].fillna('Não Informado').astype(str)
    else:
        print("AVISO: Coluna 'uf' não encontrada. Será criada com 'Não Informado'.")
        df_base['uf'] = 'Não Informado'

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
    if 'uf' not in df_mapeavel.columns: # Garante a coluna UF
         df_mapeavel['uf'] = pd.Series(dtype='object')
    print("AVISO: DataFrame base está vazio. O dashboard funcionará com dados limitados.")


# --- CONFIGURAÇÕES DO DASHBOARD ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Opções para dropdown e valores para slider
tipos_impacto_opcoes = []
if 'tipo_impacto' in df_mapeavel.columns and not df_mapeavel.empty:
    tipos_impacto_opcoes = [{'label': tipo, 'value': tipo} for tipo in sorted(df_mapeavel['tipo_impacto'].unique())]

# NOVO: Opções para o dropdown de UF
ufs_opcoes = []
if 'uf' in df_mapeavel.columns and not df_mapeavel.empty:
    ufs_opcoes = [{'label': uf, 'value': uf} for uf in sorted(df_mapeavel['uf'].unique())]


# Valores min/max para o slider, tratando df vazio
min_multa_valor_inicial = 0
max_multa_valor_inicial = 1000000
if not df_mapeavel.empty and 'valor_multa_numerico' in df_mapeavel.columns:
    min_val_temp = df_mapeavel['valor_multa_numerico'].min()
    max_val_temp = df_mapeavel['valor_multa_numerico'].max()
    if pd.notna(min_val_temp):
        min_multa_valor_inicial = float(min_val_temp) # Converter para float puro
    if pd.notna(max_val_temp):
        max_multa_valor_inicial = float(max_val_temp) # Converter para float puro
    # Garantir que max > min
    if min_multa_valor_inicial >= max_multa_valor_inicial:
        max_multa_valor_inicial = min_multa_valor_inicial + 100 # Adiciona um range se todos os valores forem iguais ou min > max

slider_step = (max_multa_valor_inicial - min_multa_valor_inicial) / 100 if (max_multa_valor_inicial - min_multa_valor_inicial) > 0 else 1


# --- Mapa de cores para a legenda customizada e o mapa ---
# Isso garante que as cores sejam as mesmas e consistentes
all_impact_types = sorted(df_mapeavel['tipo_impacto'].unique()) if not df_mapeavel.empty else []
# Usar a paleta de cores padrão do Plotly, repetindo se houver mais tipos que cores
colors = px.colors.qualitative.Plotly * (len(all_impact_types) // len(px.colors.qualitative.Plotly) + 1)
color_map = {impact_type: colors[i] for i, impact_type in enumerate(all_impact_types)}


# Colunas para a tabela de dados
colunas_tabela = [
    {"name": "Processo", "id": "numero_processo"},
    {"name": "Município", "id": "municipio"},
    {"name": "UF", "id": "uf"}, # Manter UF na tabela
    {"name": "Tipo de Impacto", "id": "tipo_impacto"},
    {"name": "Valor Multa (R$)", "id": "valor_multa_numerico_formatado", "type": "text"},
    {"name": "Descrição", "id": "descricao_impacto"}
]

# --- LAYOUT DO DASHBOARD ---
app.layout = html.Div([
    html.H1("Aecom - Valoração de Danos Ambientais", style={'textAlign': 'center', 'marginBottom': '20px'}),

    # Linha contendo Sidebar e Mapa
    html.Div([
        # Sidebar com filtros e legenda
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
            # NOVO: Dropdown para Estado/UF
            html.Label("Estado/UF:"),
            dcc.Dropdown(
                id='dropdown-uf',
                options=ufs_opcoes,
                value=[],
                multi=True,
                placeholder="Selecione o(s) estado(s)"
            ),
            html.Br(),
            html.Label("Valor da Multa (R$):"),
            dcc.RangeSlider(
                id='rangeslider-valor-multa',
                min=round(min_multa_valor_inicial, 2),
                max= round(max_multa_valor_inicial, 2),
                step=slider_step,
                value=[round(min_multa_valor_inicial, 2), round(max_multa_valor_inicial, 2)],
                tooltip={"placement": "bottom", "always_visible": True},
                marks=None
            ),
            html.Br(),
            html.Button('Limpar Filtros', id='btn-limpar-filtros', n_clicks=0, style={'marginTop': '10px', 'width': '100%'}),
            html.Hr(),
            html.Div(id='total-registros-carregados', style={'marginTop': '15px'}),
            
            html.Hr(), # Separador para a legenda
            html.Div(id='custom-legend-container') # Container para a nova legenda customizada

        ], className='sidebar', style={
            'width': '23%', 'padding': '20px', 'boxSizing': 'border-box',
            'float': 'left', 'backgroundColor': '#f9f9f9', 'borderRadius': '5px'
        }),

        # Container do Mapa
        html.Div([
            dcc.Graph(id='mapa-danos-ambientais', style={'height': '75vh'}) # Ajustar altura conforme necessário
        ], className='map-container', style={'width': '75%', 'padding': '10px', 'boxSizing': 'border-box', 'float': 'right'})

    ], style={'display': 'flex', 'flexDirection': 'row', 'marginBottom': '20px'}),

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
    ], style={'padding': '20px', 'clear': 'both'})

], style={'fontFamily': 'Arial, sans-serif', 'margin': 'auto', 'maxWidth': '1600px'})


# --- CALLBACKS DO DASHBOARD ---

# Callback para limpar filtros
@app.callback(
    [Output('dropdown-tipo-impacto', 'value'),
     Output('rangeslider-valor-multa', 'value'),
     Output('dropdown-uf', 'value')], # NOVO: Adicionado output para o dropdown de UF
    [Input('btn-limpar-filtros', 'n_clicks')],
    prevent_initial_call=True
)
def limpar_filtros(n_clicks):
    # NOVO: Resetar o valor do dropdown de UF para vazio
    return [], [min_multa_valor_inicial, max_multa_valor_inicial], []

# Callback para a legenda customizada
@app.callback(
    Output('custom-legend-container', 'children'),
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value'),
     Input('dropdown-uf', 'value')] # NOVO: Adicionado input para o dropdown de UF
)
def update_custom_legend(selected_tipos_impacto, selected_valor_multa_range, selected_ufs): # NOVO: Adicionado parâmetro
    if df_mapeavel.empty:
        return html.Details([
            html.Summary(html.Strong("Legenda do Mapa (clique para expandir/minimizar)")),
            html.Div([html.P("Nenhum dado para exibir a legenda.")], style={'padding': '10px'})
        ], open=True, style={'border': '1px solid #ddd', 'borderRadius': '5px', 'padding': '10px', 'marginTop': '10px'})

    dff = df_mapeavel.copy()

    # Aplicar os mesmos filtros que no mapa para que a legenda reflita os dados visíveis
    if selected_tipos_impacto:
        dff = dff[dff['tipo_impacto'].isin(selected_tipos_impacto)]
    if selected_valor_multa_range:
        min_val, max_val = selected_valor_multa_range
        dff = dff[(dff['valor_multa_numerico'] >= min_val) & (dff['valor_multa_numerico'] <= max_val)]
    # NOVO: Aplicar filtro de UF
    if selected_ufs:
        dff = dff[dff['uf'].isin(selected_ufs)]


    legend_items = []
    if not dff.empty:
        for impact_type in sorted(dff['tipo_impacto'].unique()):
            # Pega a cor do nosso mapa de cores fixo
            color = color_map.get(impact_type, '#CCCCCC') # Fallback color
            legend_items.append(
                html.Li([
                    html.Span(style={
                        'display': 'inline-block',
                        'width': '12px',
                        'height': '12px',
                        'borderRadius': '50%',
                        'backgroundColor': color,
                        'marginRight': '5px',
                        'verticalAlign': 'middle' # Alinhar verticalmente
                    }),
                    html.Span(impact_type, style={'verticalAlign': 'middle'})
                ], style={'marginBottom': '5px'})
            )
    else:
        legend_items.append(html.Li("Nenhum tipo de impacto encontrado com os filtros aplicados."))

    # Retorna o componente html.Details com a legenda
    return html.Details([
        html.Summary(html.Strong("Legenda do Mapa (clique para expandir/minimizar)")),
        html.Div([
            html.Ul(legend_items, style={'listStyleType': 'none', 'paddingLeft': '0', 'margin': '0'})
        ], style={'maxHeight': '40vh', 'overflowY': 'auto', 'padding': '10px'}) # Adicionado scroll e padding
    ], open=True, # Inicia expandido
    style={'border': '1px solid #ddd', 'borderRadius': '5px', 'padding': '10px', 'marginTop': '10px'})


# Callback principal para atualizar mapa, resumo e tabela
@app.callback(
    [Output('mapa-danos-ambientais', 'figure'),
     Output('resumo-resultados', 'children'),
     Output('tabela-dados-filtrados', 'data'),
     Output('total-registros-carregados', 'children')],
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value'),
     Input('dropdown-uf', 'value')] # NOVO: Adicionado input para o dropdown de UF
)
def update_dashboard(selected_tipos_impacto, selected_valor_multa_range, selected_ufs): # NOVO: Adicionado parâmetro
    # Condição para DataFrame vazio, mantendo o comportamento anterior para o mapa padrão
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
    
    # NOVO: Aplicar filtro de UF
    if selected_ufs:
        dff = dff[dff['uf'].isin(selected_ufs)]

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
            showlegend=False
        )
        resumo_texto = "Nenhum resultado para os filtros selecionados."
        dados_tabela = []
    else:
        # Formatar a coluna 'valor_multa_numerico' para a tabela
        def format_brl_currency(value):
            if pd.isna(value):
                return ""
            formatted_value = f"{value:,.2f}"
            formatted_value = formatted_value.replace('.', '#TEMP#').replace(',', '.').replace('#TEMP#', ',')
            return f"R$ {formatted_value}"

        dff['valor_multa_numerico_formatado'] = dff['valor_multa_numerico'].apply(format_brl_currency)


        fig = px.scatter_map(
            dff,
            lat="latitude",
            lon="longitude",
            color="tipo_impacto",
            color_discrete_map=color_map, # Usar o mapa de cores fixo
            hover_name="numero_processo",
            hover_data={
                "municipio": True, "uf": True, "tipo_impacto": True,
                "valor_multa_numerico": ':.2f', # Formata a multa no hover
                "descricao_impacto": True,
                "latitude": False, "longitude": False # Não mostrar lat/lon no tooltip padrão
            }
        )
        fig.update_traces(marker=dict(size=12)) # Tamanho fixo do marcador


        fig.update_layout(
            mapbox_style="carto-positron", # Ou "open-street-map"
            mapbox_zoom=4, # Zoom inicial ajustado para o Brasil
            mapbox_center={"lat": -14.2350, "lon": -51.9253}, # Centro do Brasil
            margin={"r":0,"t":0,"l":0,"b":0},
            showlegend=False # GARANTE QUE A LEGENDA NATIVA NÃO APAREÇA
        )
        num_casos = len(dff)
        media_multa = dff['valor_multa_numerico'].mean() if num_casos > 0 else 0
        soma_multa = dff['valor_multa_numerico'].sum() if num_casos > 0 else 0
        resumo_texto = (
            f"Resultados para os filtros: "
            f"<strong>{num_casos}</strong> caso(s) encontrado(s). "
            f"Valor Total das Multas: <strong>R$ {soma_multa:,.2f}</strong>. "
            f"Média da Multa: <strong>R$ {media_multa:,.2f}</strong>."
        )
        dados_tabela = dff[
            ["numero_processo", "municipio", "uf", "tipo_impacto", "valor_multa_numerico_formatado", "descricao_impacto"]
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