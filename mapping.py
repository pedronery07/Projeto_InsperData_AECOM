import pandas as pd
import folium
import re
import numpy as np
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter # Para respeitar limites da API
import time # Para o delay manual, embora RateLimiter seja melhor

# --- Funções de parsing de DMS (mesmas de antes) ---
def dms_to_dd(dms_str, original_full_ref=""):
    if pd.isna(dms_str) or not isinstance(dms_str, str) or dms_str.strip().upper() == 'NULL' or dms_str.strip() == "":
        return None
    dms_str = dms_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’")
    match = re.search(r"(\d+)\s*(?:°|º|DEG)\s*(\d+)\s*(?:’|'|MIN)\s*([\d\.]+)\s*(?:”|\"|SEC)\s*([NSEWLO])", dms_str, re.IGNORECASE)
    if not match:
        return None
    degrees, minutes, seconds, direction = match.groups()
    try:
        dd = float(degrees) + float(minutes)/60 + float(seconds)/(60*60)
    except ValueError:
        return None
    direction = direction.upper()
    if direction == 'S' or direction == 'O' or direction == 'W':
        dd *= -1
    elif direction not in ['N', 'E', 'L']:
        return None
    return dd

def parse_georreferencia(georref_str):
    original_georref_str = georref_str
    if pd.isna(georref_str) or not isinstance(georref_str, str) or georref_str.strip().upper() == 'NULL' or georref_str.strip() == "":
        return None, None
    georref_str = georref_str.strip()
    dms_single_pattern_text = r"\d+\s*(?:°|º|DEG)\s*\d+\s*(?:’|'|MIN)\s*[\d\.]+\s*(?:”|\"|SEC)\s*[NSEWLO]"
    found_coords_matches = list(re.finditer(dms_single_pattern_text, georref_str, re.IGNORECASE))

    if len(found_coords_matches) == 2:
        coord1_str = found_coords_matches[0].group(0)
        coord2_str = found_coords_matches[1].group(0)
        is_lat1 = re.search(r"[NS]$", coord1_str, re.IGNORECASE)
        is_lon1 = re.search(r"[EWLO]$", coord1_str, re.IGNORECASE)
        is_lat2 = re.search(r"[NS]$", coord2_str, re.IGNORECASE)
        is_lon2 = re.search(r"[EWLO]$", coord2_str, re.IGNORECASE)
        lat_str, lon_str = None, None
        if is_lat1 and is_lon2:
            lat_str = coord1_str; lon_str = coord2_str
        elif is_lon1 and is_lat2:
            lat_str = coord2_str; lon_str = coord1_str
        else:
            return None, None
    else:
        return None, None

    latitude_dd = dms_to_dd(lat_str, original_georref_str)
    longitude_dd = dms_to_dd(lon_str, original_georref_str)

    if latitude_dd is None or longitude_dd is None: return None, None
    if not (-90 <= latitude_dd <= 90): latitude_dd = None
    if not (-180 <= longitude_dd <= 180): longitude_dd = None
    if latitude_dd is None or longitude_dd is None: return None, None
    return latitude_dd, longitude_dd
# --- Fim das funções de parsing de DMS ---

# Carregar o arquivo Excel
excel_file_path = 'docs/respostas_danos_ambientais_df_completo.xlsx'
try:
    df = pd.read_excel(excel_file_path)
except FileNotFoundError:
    print(f"Erro: O arquivo '{excel_file_path}' não foi encontrado.")
    exit()

# Inicializar geolocator
geolocator = Nominatim(user_agent="meu_aplicativo_de_mapas_insper_aecom") # É bom ter um user_agent único
geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.1, error_wait_seconds=5.0, max_retries=2)
# Usar um cache para evitar geocodificar o mesmo lugar várias vezes
geocode_cache = {}

# Novas colunas para latitude, longitude e nível de precisão
df['latitude'] = np.nan
df['longitude'] = np.nan
df['geo_precisao'] = 'Nenhuma'

parsed_from_georef_count = 0
geocoded_by_municipio_count = 0
failed_to_geocode_count = 0

print("Iniciando processamento de georreferências e geocodificação...")
for index, row in df.iterrows():
    lat, lon = parse_georreferencia(row['georreferencia'])
    
    if lat is not None and lon is not None:
        df.loc[index, 'latitude'] = lat
        df.loc[index, 'longitude'] = lon
        df.loc[index, 'geo_precisao'] = 'Precisa (Original)'
        parsed_from_georef_count += 1
    elif pd.notna(row['municipio']) and pd.notna(row['uf']):
        municipio = str(row['municipio']).strip()
        uf = str(row['uf']).strip()
        
        # Para UFs com mais de 2 letras (ex: "Rio de Janeiro" em vez de "RJ"), pegue as duas primeiras.
        if len(uf) > 2 and uf.upper() != "DISTRITO FEDERAL": # Exceção para DF se necessário
             # Tentar um split, pode ser que o UF esteja como "Minas Gerais"
            uf_parts = uf.split()
            if len(uf_parts) > 1:
                uf_sigla_candidata = "".join([part[0] for part in uf_parts]).upper()
                # Lista de UFs válidas para conferir se a sigla faz sentido
                ufs_validas = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
                if uf_sigla_candidata in ufs_validas:
                    uf = uf_sigla_candidata
                elif uf_parts[0].upper() in ufs_validas: # Caso seja algo como "AM Manicore"
                    uf = uf_parts[0].upper()
                else: # Usa os 2 primeiros caracteres como fallback
                    uf = uf[:2].upper()
            else:
                 uf = uf[:2].upper()


        query = f"{municipio}, {uf}, Brasil"
        
        if query in geocode_cache: # Usar cache
            location = geocode_cache[query]
        else:
            print(f"  Geocodificando: {query}...")
            try:
                location = geocode_with_delay(query, timeout=10) # Adiciona timeout
                geocode_cache[query] = location # Adiciona ao cache mesmo se for None
            except Exception as e:
                print(f"    Erro durante geocodificação para {query}: {e}")
                location = None
        
        if location:
            df.loc[index, 'latitude'] = location.latitude
            df.loc[index, 'longitude'] = location.longitude
            df.loc[index, 'geo_precisao'] = 'Município (Aprox.)'
            geocoded_by_municipio_count +=1
        else:
            print(f"    Falha ao geocodificar: {query}")
            df.loc[index, 'geo_precisao'] = 'Falha na Geocodificação'
            failed_to_geocode_count += 1
    else:
        df.loc[index, 'geo_precisao'] = 'Dados Insuficientes'


print("\n--- Resumo do Processamento Geo ---")
print(f"Total de registros: {len(df)}")
print(f"Coordenadas obtidas da coluna 'georreferencia': {parsed_from_georef_count}")
print(f"Coordenadas obtidas por geocodificação de Município/UF: {geocoded_by_municipio_count}")
print(f"Falhas na geocodificação (Município/UF não encontrado ou erro): {failed_to_geocode_count}")
print(f"Registros sem coordenadas (dados insuficientes ou falha): {len(df) - parsed_from_georef_count - geocoded_by_municipio_count}")

# Filtrar linhas que possuem coordenadas válidas para o mapa
df_mapeavel = df.dropna(subset=['latitude', 'longitude'])

print(f"\nTotal de registros mapeáveis: {len(df_mapeavel)}")

if df_mapeavel.empty:
    print("Nenhum dado com coordenadas válidas encontrado para gerar o mapa.")
    # (código para HTML vazio omitido para brevidade)
else:
    map_center_lat = df_mapeavel['latitude'].mean()
    map_center_lon = df_mapeavel['longitude'].mean()
    
    if pd.isna(map_center_lat) or pd.isna(map_center_lon):
        map_center_lat = -14.2350
        map_center_lon = -51.9253

    m = folium.Map(location=[map_center_lat, map_center_lon], zoom_start=5)

    for idx, row in df_mapeavel.iterrows():
        def get_str(val, default='N/A'): return str(val) if pd.notna(val) else default
        
        numero_processo = get_str(row.get('numero_processo'))
        municipio = get_str(row.get('municipio'))
        uf_map = get_str(row.get('uf')) # Renomeado para evitar conflito com variável 'uf' no loop de geocodificação
        responsavel = get_str(row.get('responsavel'))
        tipo_impacto = get_str(row.get('tipo_impacto'))
        descricao_impacto = get_str(row.get('descricao_impacto'))
        
        data_impacto_val = row.get('data_impacto')
        data_impacto = pd.to_datetime(data_impacto_val, errors='coerce').strftime('%d/%m/%Y') if pd.notna(data_impacto_val) and not isinstance(data_impacto_val, str) else get_str(data_impacto_val)
        if data_impacto == 'NaT': data_impacto = get_str(data_impacto_val)


        area_afetada = get_str(row.get('area_afetada'))
        unidade_area = get_str(row.get('unidade_area'), '')
        area_completa = f"{area_afetada} {unidade_area}".strip()
        if area_completa == "N/A" or area_completa == "N/A N/A" or area_completa == "N/A ": area_completa = "N/A"
        
        valor_multa_val = row.get('valor_multa')
        if pd.notna(valor_multa_val):
            try: valor_multa = f"R$ {float(valor_multa_val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except (ValueError, TypeError): valor_multa = get_str(valor_multa_val)
        else: valor_multa = "N/A"

        geo_precisao_info = get_str(row.get('geo_precisao'))

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 12px; max-width: 350px;">
            <h4 style="margin-bottom: 5px;">Detalhes do Dano Ambiental</h4>
            <p><strong>Nº Processo:</strong> {numero_processo}</p>
            <p><strong>Local:</strong> {municipio} - {uf_map} <i>({geo_precisao_info})</i></p>
            <p><strong>Responsável:</strong> {responsavel}</p>
            <p><strong>Tipo de Impacto:</strong> {tipo_impacto}</p>
            <p><strong>Descrição:</strong> {descricao_impacto[:250] + '...' if len(descricao_impacto) > 250 else descricao_impacto}</p>
            <p><strong>Data do Impacto:</strong> {data_impacto}</p>
            <p><strong>Área Afetada:</strong> {area_completa}</p>
            <p><strong>Valor Multa:</strong> {valor_multa}</p>
        </div>
        """
        iframe = folium.IFrame(html=popup_html, width=380, height=320) # Ajustado width/height
        popup = folium.Popup(iframe, max_width=380)
        
        # Diferenciar cor do marcador pela precisão
        cor_marcador = 'blue' # Default
        if geo_precisao_info == 'Precisa (Original)':
            cor_marcador = 'green'
        elif geo_precisao_info == 'Município (Aprox.)':
            cor_marcador = 'orange'
        
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=popup,
            tooltip=f"{tipo_impacto} em {municipio} ({geo_precisao_info})",
            icon=folium.Icon(color=cor_marcador, icon='info-sign' if geo_precisao_info != 'Precisa (Original)' else 'pushpin')
        ).add_to(m)

    map_file_path = "mapa_danos_ambientais.html"
    m.save(map_file_path)
    print(f"\nMapa gerado e salvo como '{map_file_path}'")
    print(f"Para visualizar, abra o arquivo '{map_file_path}' em um navegador web.")