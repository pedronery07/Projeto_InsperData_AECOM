import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go # Para mais controle sobre o mapa
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import numpy as np
import re

# Suas funções de geocodificação e processamento de dados (parse_georreferencia, dms_to_dd, etc.)
# iriam aqui ou seriam importadas de outro arquivo.

# --- Funções de parsing de DMS (mesmas de antes, omitidas para brevidade no exemplo) ---
def dms_to_dd(dms_str, original_full_ref=""):
    if pd.isna(dms_str) or not isinstance(dms_str, str) or dms_str.strip().upper() == 'NULL' or dms_str.strip() == "": return None
    dms_str = dms_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’")
    match = re.search(r"(\d+)\s*(?:°|º|DEG)\s*(\d+)\s*(?:’|'|MIN)\s*([\d\.]+)\s*(?:”|\"|SEC)\s*([NSEWLO])", dms_str, re.IGNORECASE)
    if not match: return None
    degrees, minutes, seconds, direction = match.groups()
    try: dd = float(degrees) + float(minutes)/60 + float(seconds)/(60*60)
    except ValueError: return None
    direction = direction.upper()
    if direction == 'S' or direction == 'O' or direction == 'W': dd *= -1
    elif direction not in ['N', 'E', 'L']: return None
    return dd

def parse_georreferencia(georref_str):
    original_georref_str = georref_str
    if pd.isna(georref_str) or not isinstance(georref_str, str) or georref_str.strip().upper() == 'NULL' or georref_str.strip() == "": return None, None
    georref_str = georref_str.strip()
    dms_single_pattern_text = r"\d+\s*(?:°|º|DEG)\s*\d+\s*(?:’|'|MIN)\s*[\d\.]+\s*(?:”|\"|SEC)\s*[NSEWLO]"
    found_coords_matches = list(re.finditer(dms_single_pattern_text, georref_str, re.IGNORECASE))
    if len(found_coords_matches) == 2:
        coord1_str, coord2_str = found_coords_matches[0].group(0), found_coords_matches[1].group(0)
        is_lat1, is_lon1 = re.search(r"[NS]$", coord1_str, re.IGNORECASE), re.search(r"[EWLO]$", coord1_str, re.IGNORECASE)
        is_lat2, is_lon2 = re.search(r"[NS]$", coord2_str, re.IGNORECASE), re.search(r"[EWLO]$", coord2_str, re.IGNORECASE)
        lat_str, lon_str = (coord1_str, coord2_str) if is_lat1 and is_lon2 else (coord2_str, coord1_str) if is_lon1 and is_lat2 else (None, None)
        if not lat_str: return None, None
    else: return None, None
    latitude_dd, longitude_dd = dms_to_dd(lat_str, original_georref_str), dms_to_dd(lon_str, original_georref_str)
    if latitude_dd is None or longitude_dd is None: return None, None
    if not (-90 <= latitude_dd <= 90): latitude_dd = None
    if not (-180 <= longitude_dd <= 180): longitude_dd = None
    if latitude_dd is None or longitude_dd is None: return None, None
    return latitude_dd, longitude_dd
# --- Fim das funções de parsing de DMS ---

# Carregar o arquivo Excel
excel_file_path = 'docs/respostas_danos_ambientais_df_parte0.xlsx' # Certifique-se que este é o nome correto
try:
    df = pd.read_excel(excel_file_path)
except FileNotFoundError:
    print(f"Erro: O arquivo '{excel_file_path}' não foi encontrado.")
    exit()

# Limpar e converter 'valor_multa' para numérico, tratando erros
df['valor_multa_numerico'] = pd.to_numeric(df['valor_multa'], errors='coerce').fillna(0)
# Garantir que tipo_impacto não tenha NaNs para evitar problemas com chaves de dicionário
df['tipo_impacto'] = df['tipo_impacto'].fillna('Não Especificado')


# Inicializar geolocator e cache (como antes)
geolocator = Nominatim(user_agent="meu_aplicativo_de_mapas_insper_aecom_v3_debug") # Mudei user_agent
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.1, error_wait_seconds=5.0, max_retries=2)
geocode_cache = {}

df['latitude'] = np.nan
df['longitude'] = np.nan
df['geo_precisao'] = 'Nenhuma'
parsed_from_georef_count = 0
geocoded_by_municipio_count = 0
failed_to_geocode_count = 0 # Adicionado contador

print("Iniciando processamento de georreferências e geocodificação...")
for index, row in df.iterrows():
    lat, lon = parse_georreferencia(row['georreferencia'])
    if lat is not None and lon is not None:
        df.loc[index, 'latitude'], df.loc[index, 'longitude'] = lat, lon
        df.loc[index, 'geo_precisao'] = 'Precisa (Original)'
        parsed_from_georef_count += 1
    elif pd.notna(row['municipio']) and pd.notna(row['uf']):
        municipio, uf_original = str(row['municipio']).strip(), str(row['uf']).strip()
        # Lógica UF (pode precisar de ajuste se UFs forem complexas)
        uf_parts = uf_original.split()
        uf = uf_parts[0][:2].upper() if uf_parts else uf_original[:2].upper()

        query = f"{municipio}, {uf}, Brasil"
        if query in geocode_cache: location = geocode_cache[query]
        else:
            # print(f"  Geocodificando: {query}...") # Comentado para reduzir output se funcionar
            try:
                location = geocode_with_delay(query, timeout=10)
                geocode_cache[query] = location
            except Exception as e:
                print(f"    Erro durante geocodificação para {query}: {e}"); location = None
        if location:
            df.loc[index, 'latitude'], df.loc[index, 'longitude'] = location.latitude, location.longitude
            df.loc[index, 'geo_precisao'] = 'Município (Aprox.)'
            geocoded_by_municipio_count += 1
        else:
            # print(f"    Falha ao geocodificar: {query}") # Comentado para reduzir output
            df.loc[index, 'geo_precisao'] = 'Falha na Geocodificação'
            failed_to_geocode_count +=1
    else:
        df.loc[index, 'geo_precisao'] = 'Dados Insuficientes'

print("\n--- Resumo do Processamento Geo ---")
print(f"Total de registros no arquivo: {len(df)}")
print(f"Coordenadas obtidas da coluna 'georreferencia': {parsed_from_georef_count}")
print(f"Coordenadas obtidas por geocodificação de Município/UF: {geocoded_by_municipio_count}")
print(f"Falhas na geocodificação (Município/UF não encontrado ou erro): {failed_to_geocode_count}")
registros_sem_coords = len(df) - parsed_from_georef_count - geocoded_by_municipio_count
print(f"Registros sem coordenadas (dados insuficientes ou falha total): {registros_sem_coords}")


df_mapeavel = df.dropna(subset=['latitude', 'longitude']).copy()

print(f"\nTotal de registros mapeáveis (com lat/lon): {len(df_mapeavel)}")

# ---- DEBUG ADICIONAL PARA df_mapeavel ----
if not df_mapeavel.empty:
    print("\n--- Amostra e Informações de df_mapeavel ---")
    print(df_mapeavel[['numero_processo', 'municipio', 'uf', 'tipo_impacto', 'valor_multa', 'valor_multa_numerico', 'latitude', 'longitude', 'geo_precisao']].head())
    print(f"\nTipos de impacto únicos em df_mapeavel: {df_mapeavel['tipo_impacto'].unique()}")
    print(f"\nEstatísticas de 'valor_multa_numerico' em df_mapeavel:\n{df_mapeavel['valor_multa_numerico'].describe()}")
    print("--------------------------------------------\n")
else:
    print("\nDF_MAPEAVEL ESTÁ VAZIO. Nenhum marcador será criado.")
# ---- FIM DEBUG ADICIONAL ----

# --- INÍCIO DA LÓGICA DE CARREGAMENTO E PROCESSAMENTO DE DADOS ---
# (Reutilize o código que já temos para carregar o Excel,
#  processar georreferencia, geocodificar por município/UF,
#  e criar df_mapeavel)

# Exemplo simplificado de dados (substitua pelo seu carregamento real)
# df_mapeavel = pd.DataFrame({
#     'latitude': [-5.8, -7.7, -3.2],
#     'longitude': [-61.2, -61.4, -52.2],
#     'tipo_impacto': ['Desmatamento', 'Desmatamento de APP', 'Poluição Hídrica'],
#     'valor_multa_numerico': [1000, 50000, 200],
#     'municipio': ['Manicoré', 'Manicoré', 'Altamira'],
#     'numero_processo': ['P1', 'P2', 'P3'],
#     'descricao_impacto': ['Desc1', 'Desc2', 'Desc3']
# })
# Supondo que df_mapeavel está carregado e processado aqui
# ... (seu código de processamento de dados existente) ...
# Certifique-se de que df_mapeavel está disponível globalmente ou passado corretamente

# --- FIM DA LÓGICA DE CARREGAMENTO E PROCESSAMENTO DE DADOS ---

# Inicializar o app Dash
app = dash.Dash(__name__)

# --- CARREGUE E PROCESSE SEUS DADOS AQUI ---
# Coloque aqui o código para carregar seu Excel e gerar df_mapeavel
# Exemplo:
excel_file_path = 'docs/respostas_danos_ambientais_df_parte0.xlsx'
df_completo = pd.read_excel(excel_file_path)
df_completo['valor_multa_numerico'] = pd.to_numeric(df_completo['valor_multa'], errors='coerce').fillna(0)
df_completo['tipo_impacto'] = df_completo['tipo_impacto'].fillna('Não Especificado')
# ... (adicione sua lógica de geocodificação para popular lat/lon) ...
# df_mapeavel = df_completo.dropna(subset=['latitude', 'longitude'])
# Por simplicidade, vou criar um df_mapeavel de exemplo aqui, mas você usará o seu.
# Assume-se que df_mapeavel é o DataFrame final com lat, lon, tipo_impacto, valor_multa_numerico
# e outras colunas para o hover/popup.

# === SUBSTITUA ESTE BLOCO COM SEU CARREGAMENTO DE DADOS E GEOCODIFICAÇÃO ===
# Carregar o arquivo Excel
try:
    df = pd.read_excel(excel_file_path)
except FileNotFoundError:
    print(f"Erro: O arquivo '{excel_file_path}' não foi encontrado.")
    exit()

df['valor_multa_numerico'] = pd.to_numeric(df['valor_multa'], errors='coerce').fillna(0)
df['tipo_impacto'] = df['tipo_impacto'].fillna('Não Especificado')
# ... (Sua lógica de geocodificação para criar df['latitude'] e df['longitude']) ...
# Substitua este placeholder com seu df_mapeavel real
data_exemplo = {
    'numero_processo': [f'Proc{i}' for i in range(1, 23)],
    'municipio': ['Manicoré', 'Manicoré', 'Manicoré', 'Altamira', 'Marabá', 'Manicoré', 'Aparecida de Goiânia', 'Ipameri', 'Aracati', 'Vila Velha', 'Caldas Novas', 'Goianira', 'Manaus', 'Manaus', 'Manaus', 'Pedra Azul', 'Jacuí', 'Varginha', 'Goiânia', 'Varginha', 'Rio Casca', 'Rio Casca'],
    'uf': ['AM', 'AM', 'AM', 'PA', 'PA', 'AM', 'GO', 'GO', 'CE', 'ES', 'GO', 'GO', 'AM', 'AM', 'AM', 'MG', 'MG', 'MG', 'GO', 'MG', 'MG', 'MG'],
    'tipo_impacto': ['Desmatamento', 'Desmatamento de APP', 'Lançamento e queima de rejeitos de indústria madeireira', 'Desmatamento', 'Desmatamento de APP', 'Desmatamento de Floresta Amazônica', 'Poluição Hídrica', 'Interrupção no fornecimento de energia elétrica', 'Ocupação Irregular de Terreno', 'Poluição Sonora', 'Publicidade Enganosa e Atraso na Entrega de Imóvel', 'Infraestrutura Irregular', 'Abastecimento Irregular de Água', 'Abastecimento irregular de água', 'Interrupção no fornecimento de água', 'Desmatamento de APP', 'Desmatamento de APP', 'Poluição Hídrica', 'Danos a poste de energia elétrica', 'Desmatamento de APP', 'Assoreamento', 'Desmatamento de APP'],
    'valor_multa_numerico': [0, 0, 24240, 0, 0, 1423100.16, 15000, 38285.91, 0, 0, 0, 0, 1200, 3000, 3000, 59127.63, 4528.76, 20000, 26459.25, 0, 0, 0],
    'latitude': [-5.80, -7.71, -5.80, -3.20, -5.34, -5.81, -16.82, -17.73, -4.56, -20.35, -17.75, -16.57, -3.11, -3.12, -3.13, -16.10, -21.01, -21.58, -16.68, -21.59, -20.26, -20.27],
    'longitude': [-61.28, -61.46, -61.28, -52.20, -49.10, -61.29, -49.31, -48.15, -37.77, -40.30, -48.62, -49.43, -60.02, -60.03, -60.04, -41.28, -46.74, -45.46, -49.25, -45.47, -42.78, -42.79],
    'descricao_impacto': ['Desc...' for _ in range(22)]
}
df_mapeavel = pd.DataFrame(data_exemplo) # Certifique-se que este df_mapeavel é o seu real
# === FIM DO BLOCO DE CARREGAMENTO DE DADOS ===


app = dash.Dash(__name__, suppress_callback_exceptions=True) # Adicionado suppress_callback_exceptions

tipos_impacto_opcoes = [{'label': tipo, 'value': tipo} for tipo in sorted(df_mapeavel['tipo_impacto'].unique())]
max_multa_valor = df_mapeavel['valor_multa_numerico'].max() if not df_mapeavel.empty else 1000000
min_multa_valor = df_mapeavel['valor_multa_numerico'].min() if not df_mapeavel.empty else 0


app.layout = html.Div([
    html.H1("AECOM: Valoração de Danos Ambientais (Dash/Plotly)"),
    html.Div([
        html.Div([
            html.Label("Tipo de Impacto:"),
            dcc.Dropdown(
                id='dropdown-tipo-impacto',
                options=tipos_impacto_opcoes,
                value=[], # Começar com nada selecionado
                multi=True,
                placeholder="Selecione o(s) tipo(s) de impacto"
            ),
            html.Br(),
            html.Label("Valor da Multa (R$):"),
            dcc.RangeSlider(
                id='rangeslider-valor-multa',
                min=min_multa_valor,
                max=max_multa_valor,
                step= (max_multa_valor - min_multa_valor) / 1000 if (max_multa_valor - min_multa_valor) > 0 else 1, # Passo dinâmico
                value=[min_multa_valor, max_multa_valor],
                tooltip={"placement": "bottom", "always_visible": True},
                marks=None # Remover marcas por enquanto para não poluir
            ),
        ], className='sidebar', style={'width': '25%', 'padding': '20px', 'box-sizing': 'border-box'}),

        html.Div([
            dcc.Graph(id='mapa-danos-ambientais', style={'height': '80vh'}) # Aumentar altura do mapa
        ], className='map-container', style={'width': '75%', 'padding': '10px', 'box-sizing': 'border-box'})
    ], style={'display': 'flex', 'flex-direction': 'row'}),
    html.Div(id='resumo-resultados')
])

@app.callback(
    [Output('mapa-danos-ambientais', 'figure'),
     Output('resumo-resultados', 'children')],
    [Input('dropdown-tipo-impacto', 'value'),
     Input('rangeslider-valor-multa', 'value')]
)
def update_map_and_summary(selected_tipos_impacto, selected_valor_multa_range):
    dff = df_mapeavel.copy()

    if selected_tipos_impacto:
        dff = dff[dff['tipo_impacto'].isin(selected_tipos_impacto)]

    if selected_valor_multa_range:
        min_val, max_val = selected_valor_multa_range
        dff = dff[(dff['valor_multa_numerico'] >= min_val) & (dff['valor_multa_numerico'] <= max_val)]

    if dff.empty:
        fig = go.Figure(go.Scattermapbox(lat=[], lon=[]))
        fig.update_layout(
            mapbox_style="carto-positron",
            mapbox_zoom=3,
            mapbox_center={"lat": -14.2350, "lon": -51.9253},
            margin={"r":0,"t":0,"l":0,"b":0},
        )
        resumo_texto = "Nenhum resultado para os filtros selecionados."
    else:
        # Adicionar coluna para tamanho fixo dos marcadores
        dff_map_plot = dff.copy() # Evitar SettingWithCopyWarning
        dff_map_plot.loc[:, 'marker_size'] = 10 # Tamanho base para os marcadores

        fig = px.scatter_map(
            dff_map_plot,
            lat="latitude",
            lon="longitude",
            color="tipo_impacto",
            size='marker_size', # Usar o tamanho fixo
            size_max=20,        # Tamanho visual no mapa
            hover_name="numero_processo",
            hover_data={
                "municipio": True, "uf": True, "tipo_impacto": True,
                "valor_multa_numerico": ':.2f', "descricao_impacto": True,
                "latitude": False, "longitude": False, 'marker_size': False
            },
            zoom=3.5,
            center={"lat": dff['latitude'].mean(), "lon": dff['longitude'].mean()},
        )
        fig.update_layout(
            mapbox_style="carto-positron", # Estilo mais limpo
            margin={"r":0,"t":0,"l":0,"b":0},
            legend=dict(
                yanchor="top", y=0.99, xanchor="left", x=0.01,
                bgcolor="rgba(255,255,255,0.8)", bordercolor="Gray", borderwidth=1,
                title_text='Tipo de Impacto'
            )
        )
        num_casos = len(dff)
        media_multa = dff['valor_multa_numerico'].mean() if num_casos > 0 else 0
        resumo_texto = f"Resultados para os filtros: {num_casos} casos. Média da Multa: R$ {media_multa:,.2f}"

    return fig, resumo_texto

if __name__ == '__main__':
    app.run(debug=True)