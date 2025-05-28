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

# Opções para o dropdown de UF
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
# MUDANÇA: Usando uma paleta de cores Plotly mais genérica que se encaixa bem
# (Plotly original é uma boa base para muitas cores)
all_impact_types = sorted(df_mapeavel['tipo_impacto'].unique()) if not df_mapeavel.empty else []
# Definir a paleta de cores. Você pode experimentar com outras aqui, como 'Plotly', 'D3', 'Set1', 'Dark2', etc.
# Usaremos 'Plotly' como base, que tem um bom contraste e cores variadas.
colors = px.colors.qualitative.Plotly * (len(all_impact_types) // len(px.colors.qualitative.Plotly) + 1) # Repete a paleta se necessário
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
    # MUDANÇA: Container para os logos e o título
    html.Div(style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center', 'marginBottom': '20px'}),
    html.Div([
        html.Img(src=app.get_asset_url('aecom.png'), style={'height': '50px', 'marginRight': '20px'}), # Logo Aecom
        html.H1("Valoração de Danos Ambientais", style={'textAlign': 'center', 'color': '#212529', 'margin': '0'}), # Título principal
        html.Img(src=app.get_asset_url('data.png'), style={'height': '50px', 'marginLeft': '20px'}) # Logo Insper Data
    ], style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center', 'marginBottom': '20px'}),


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
                max=round(max_multa_valor_inicial, 2),
                step=slider_step,
                value=[round(min_multa_valor_inicial, 2), round(max_multa_valor_inicial, 2)],
            
                tooltip={"placement": "bottom", "always_visible": True},
                marks=None
            ),
            html.Br(),
            html.Button('Limpar Filtros', id='btn-limpar-filtros', n_clicks=0, style={'marginTop': '10px', 'width': '100%', 'backgroundColor': '#007bff', 'color': 'white', 'border': 'none', 'padding': '10px 15px', 'borderRadius': '5px', 'cursor': 'pointer'}), # MUDANÇA: Cor do botão
            html.Hr(),
            html.Div(id='total-registros-carregados', style={'marginTop': '15px'}),
            
            html.Hr(), # Separador para a legenda
            html.Div(id='custom-legend-container') # Container para a nova legenda customizada

        ], className='sidebar', style={
            'width': '23%', 'padding': '20px', 'boxSizing': 'border-box',
            'float': 'left', 'backgroundColor': '#F8F9FA', 'borderRadius': '5px' # MUDANÇA: Cor de fundo da sidebar
        }),

        # Container do Mapa e novo gráfico
        html.Div([
            dcc.Graph(id='mapa-danos-ambientais', style={'height': '75vh'}),
            html.Div([
                dcc.Graph(id='bar-chart-avg-multa', style={'height': '40vh', 'marginTop': '20px'})
            ])
        ], className='map-and-chart-container', style={'width': '75%', 'padding': '10px', 'boxSizing': 'border-box', 'float': 'right'})

    ], style={'display': 'flex', 'flexDirection': 'row', 'marginBottom': '20px'}),

    # Resumo e Tabela de Dados
    html.Div([
        html.H4("Resumo e Dados Filtrados", style={'textAlign': 'center'}),
        # MUDANÇA: Cor de fundo do resumo de resultados
        html.Div(id='resumo-resultados', style={'padding': '10px', 'textAlign': 'center', 'fontWeight': 'bold', 'backgroundColor': '#E0F2F7', 'borderRadius': '5px', 'marginBottom': '10px'}), # Light blue
        dash_table.DataTable(
            id='tabela-dados-filtrados',
            columns=colunas_tabela,
            data=[], # Inicialmente vazia
            page_size=10,
            style_cell={'textAlign': 'center',
                        'fontFamily': 'Arial, sans-serif',
                        'minWidth': '100px',
                        'width': '150px',
                        'maxWidth': '300px',
                        'overflow': 'hidden', 
                        'textOverflow': 'ellipsis'},
            # MUDANÇA: Cor de fundo do cabeçalho da tabela
            style_header={'backgroundColor': '#E9ECEF', 'fontWeight': 'bold'}, # Slightly darker gray than F8F9FA
            style_data={'whiteSpace': 'normal', 'height': 'auto'},
            filter_action="native",
            sort_action="native",
            export_format="xlsx",
            export_headers="display"
        )
    ], style={'padding': '20px', 'clear': 'both'})

], style={'fontFamily': 'Arial, sans-serif', 'margin': 'auto', 'maxWidth': '1600px', 'backgroundColor': '#FFFFFF'}) # Fundo geral mais claro, se quiser


# --- CALLBACKS DO DASHBOARD ---

# Callback para limpar filtros
@app.callback(
    [Output('dropdown-tipo-impacto', 'value'),
     Output('rangeslider-valor-multa', 'value'),
     Output('dropdown-uf', 'value')],
    [Input('btn-limpar-filtros', 'n_clicks')],
    prevent_initial_call=True
)
def limpar_filtros(n_clicks):
    return [], [min_multa_valor_inicial, max_multa_valor_inicial], []

# Callback para a legenda customizada
@app.callback(
    Output('custom-legend-container', 'children'),
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value'),
     Input('dropdown-uf', 'value')]
)
def update_custom_legend(selected_tipos_impacto, selected_valor_multa_range, selected_ufs):
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
        ], style={'maxHeight': '40vh', 'overflowY': 'auto', 'padding': '10px'})
    ], open=True,
    # MUDANÇA: Cor da borda da legenda customizada
    style={'border': '1px solid #CED4DA', 'borderRadius': '5px', 'padding': '10px', 'marginTop': '10px'}) # Lighter gray border


# Callback principal para atualizar mapa, resumo e tabela (e o novo gráfico)
@app.callback(
    [Output('mapa-danos-ambientais', 'figure'),
     Output('bar-chart-avg-multa', 'figure'),
     Output('resumo-resultados', 'children'),
     Output('tabela-dados-filtrados', 'data'),
     Output('total-registros-carregados', 'children')],
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value'),
     Input('dropdown-uf', 'value')]
)
def update_dashboard(selected_tipos_impacto, selected_valor_multa_range, selected_ufs):
    # Condição para DataFrame vazio, preparando figuras default para todos os outputs
    default_fig_map = go.Figure(go.Scattermap(lat=[], lon=[]))
    default_fig_map.update_layout(mapbox_style="carto-positron", mapbox_zoom=2.5,
                                  mapbox_center={"lat": -14.2350, "lon": -51.9253},
                                  margin={"r":0,"t":0,"l":0,"b":0}, showlegend=False)
    
    default_fig_bar_avg = go.Figure().update_layout(
        title="Valor Médio da Multa por Tipo de Impacto",
        xaxis_title="Tipo de Impacto",
        yaxis_title="Valor Médio da Multa (R$)"
    )

    resumo_texto = "Nenhum dado carregado para exibir."
    dados_tabela = []
    total_carregados_texto = f"Total de registros no arquivo original: {len(df_base)}"

    if df_mapeavel.empty:
        return default_fig_map, default_fig_bar_avg, resumo_texto, dados_tabela, total_carregados_texto

    dff = df_mapeavel.copy() # Começa com todos os dados mapeáveis

    # Aplicar filtros
    if selected_tipos_impacto:
        dff = dff[dff['tipo_impacto'].isin(selected_tipos_impacto)]
    if selected_valor_multa_range:
        min_val, max_val = selected_valor_multa_range
        dff = dff[(dff['valor_multa_numerico'] >= min_val) & (dff['valor_multa_numerico'] <= max_val)]
    if selected_ufs:
        dff = dff[dff['uf'].isin(selected_ufs)]

    total_carregados_texto = f"Registros mapeáveis carregados: {len(df_mapeavel)} (de {len(df_base)} no total)"

    # Gerar os gráficos e a tabela
    if dff.empty:
        resumo_texto = "Nenhum resultado para os filtros selecionados."
        dados_tabela = []
        return default_fig_map, default_fig_bar_avg, resumo_texto, dados_tabela, total_carregados_texto
    else:
        # Formatar a coluna 'valor_multa_numerico' para a tabela
        def format_brl_currency(value):
            if pd.isna(value):
                return ""
            formatted_value = f"{value:,.2f}"
            formatted_value = formatted_value.replace('.', '#TEMP#').replace(',', '.').replace('#TEMP#', ',')
            return f"R$ {formatted_value}"

        dff['valor_multa_numerico_formatado'] = dff['valor_multa_numerico'].apply(format_brl_currency)


        # MAPA
        fig_map = px.scatter_map(
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
        fig_map.update_traces(marker=dict(size=12)) # Tamanho fixo do marcador para visibilidade


        fig_map.update_layout(
            mapbox_style="carto-positron", # Ou "open-street-map"
            mapbox_zoom=4, # Zoom inicial ajustado para o Brasil
            mapbox_center={"lat": -14.2350, "lon": -51.9253}, # Centro do Brasil
            margin={"r":0,"t":0,"l":0,"b":0},
            showlegend=False # GARANTE QUE A LEGENDA NATIVA NÃO APAREÇA
        )

        # Gráfico de Barras - Preço Médio da Multa por Tipo de Impacto
        df_avg_multa_by_impact = dff.groupby('tipo_impacto')['valor_multa_numerico'].mean().reset_index()
        df_avg_multa_by_impact.columns = ['Tipo de Impacto', 'Valor Médio da Multa']
        df_avg_multa_by_impact = df_avg_multa_by_impact.sort_values(by='Valor Médio da Multa', ascending=False)

        fig_bar_avg = px.bar(
            df_avg_multa_by_impact,
            x='Tipo de Impacto',
            y='Valor Médio da Multa',
            title='Valor Médio da Multa por Tipo de Impacto',
            color='Tipo de Impacto', # Colorir as barras pelo tipo de impacto
            color_discrete_map=color_map, # Usar o mapa de cores fixo
            hover_data={'Valor Médio da Multa': ':.2f'}
        )
        fig_bar_avg.update_layout(
            xaxis_title="Tipo de Impacto",
            yaxis_title="Valor Médio da Multa (R$)",
            showlegend=False
        )
        fig_bar_avg.update_yaxes(tickprefix='R$ ')


        # Resumo de texto
        num_casos = len(dff)
        media_multa = dff['valor_multa_numerico'].mean()
        soma_multa = dff['valor_multa_numerico'].sum()
        resumo_texto = (
            f"Resultados para os filtros: "
            f"{num_casos} caso(s) encontrado(s). "
            f"Valor Total das Multas: R$ {soma_multa:,.2f}. "
            f"Média da Multa: R$ {media_multa:,.2f}."
        )
        dados_tabela = dff[
            ["numero_processo", "municipio", "uf", "tipo_impacto", "valor_multa_numerico_formatado", "descricao_impacto"]
        ].to_dict('records')

    return fig_map, fig_bar_avg, resumo_texto, dados_tabela, total_carregados_texto


# --- RODAR O APLICATIVO DASH ---
if __name__ == '__main__':
    # Certifique-se de que a pasta 'img' existe
    assets_folder = os.path.join(os.path.dirname(__file__), 'assets')
    if not os.path.exists(assets_folder):
        os.makedirs(assets_folder)
        print(f"Pasta 'assets' criada em: {assets_folder}")
    
    # Se os arquivos .png não existirem na pasta assets, avise o usuário
    for logo_name in ['data.png', 'aecom.png']:
        logo_path = os.path.join(assets_folder, logo_name)
        if not os.path.exists(logo_path):
            print(f"AVISO: O arquivo '{logo_path}' não foi encontrado.")
            print(f"Por favor, coloque '{logo_name}' na pasta '{assets_folder}' para que os logos apareçam corretamente.")


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