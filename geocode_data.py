# geocode_data.py

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import numpy as np
import re
import time # Para medir o tempo
import os # Para criar o diretório 'docs'

# --- Funções de parsing de DMS (exatamente como você forneceu) ---
def dms_to_dd(dms_str, original_full_ref=""):
    if pd.isna(dms_str) or not isinstance(dms_str, str) or dms_str.strip().upper() == 'NULL' or dms_str.strip() == "": return None
    # Normalizações adicionais para caracteres problemáticos
    dms_str = dms_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’")
    dms_str = dms_str.replace("`", "’") # tratar acento grave como apóstrofo
    
    # Tenta capturar graus, minutos, segundos (com ou sem decimais) e direção
    # Padrão mais robusto para aceitar variações
    match = re.search(r"(\d+)\s*(?:°|º|DEG|GRAUS|\s)\s*(\d+)\s*(?:’|'|MIN|\s)\s*([\d\.,]+)\s*(?:”|\"|SEC|\s)\s*([NSEWLO])", dms_str, re.IGNORECASE)
    
    if not match:
        # Tenta um padrão mais simples se o primeiro falhar (ex: apenas graus e minutos com direção)
        match_simple = re.search(r"(\d+)\s*(?:°|º|DEG|GRAUS)\s*([\d\.,]+)\s*(?:’|'|MIN)\s*([NSEWLO])", dms_str, re.IGNORECASE)
        if match_simple:
            degrees, minutes, direction = match_simple.groups()
            seconds = "0" # Assume 0 segundos
        else:
            # print(f"Debug dms_to_dd: Padrão não correspondeu para '{dms_str}' em '{original_full_ref}'")
            return None
    else:
        degrees, minutes, seconds, direction = match.groups()

    try:
        # Substituir vírgula por ponto para decimais
        seconds = seconds.replace(',', '.')
        minutes = minutes.replace(',', '.')
        
        dd = float(degrees) + float(minutes)/60 + float(seconds)/(60*60)
    except ValueError as e:
        # print(f"Debug dms_to_dd: Erro de conversão para float em '{dms_str}' (original: '{original_full_ref}'). Detalhe: {e}")
        return None
        
    direction = direction.upper()
    if direction == 'S' or direction == 'O' or direction == 'W':
        dd *= -1
    elif direction not in ['N', 'E', 'L']: # L para Leste
        # print(f"Debug dms_to_dd: Direção inválida '{direction}' em '{dms_str}' (original: '{original_full_ref}')")
        return None
    return dd

def parse_georreferencia(georref_str):
    original_georref_str = georref_str # Para debug
    if pd.isna(georref_str) or not isinstance(georref_str, str) or georref_str.strip().upper() == 'NULL' or georref_str.strip() == "":
        return None, None
    
    georref_str = georref_str.strip()
    # Normaliza aspas e outros caracteres comuns
    georref_str = georref_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’").replace("`", "’")

    # Padrão para uma coordenada DMS completa (graus, minutos, segundos, direção)
    # Aceita variações de espaçamento e separadores
    dms_single_pattern_text = r"\d+\s*(?:°|º|DEG|GRAUS|\s)\s*\d+\s*(?:’|'|MIN|\s)\s*[\d\.,]+\s*(?:”|\"|SEC|\s)\s*[NSEWLO]"
    # Padrão alternativo mais simples (graus, minutos com decimais, direção)
    dms_simple_pattern_text = r"\d+\s*(?:°|º|DEG|GRAUS)\s*[\d\.,]+\s*(?:’|'|MIN)\s*[NSEWLO]"

    found_coords_matches = list(re.finditer(dms_single_pattern_text, georref_str, re.IGNORECASE))
    
    if len(found_coords_matches) < 2: # Se não encontrou duas coordenadas DMS completas, tenta o padrão mais simples
        found_coords_matches = list(re.finditer(dms_simple_pattern_text, georref_str, re.IGNORECASE))

    latitude_dd, longitude_dd = None, None

    if len(found_coords_matches) == 2:
        coord1_str = found_coords_matches[0].group(0)
        coord2_str = found_coords_matches[1].group(0)

        # Tenta identificar qual é latitude e qual é longitude pela direção
        is_lat1 = bool(re.search(r"[NS]$", coord1_str, re.IGNORECASE))
        is_lon1 = bool(re.search(r"[EWLO]$", coord1_str, re.IGNORECASE))
        is_lat2 = bool(re.search(r"[NS]$", coord2_str, re.IGNORECASE))
        is_lon2 = bool(re.search(r"[EWLO]$", coord2_str, re.IGNORECASE))

        lat_str, lon_str = None, None
        if is_lat1 and is_lon2:
            lat_str, lon_str = coord1_str, coord2_str
        elif is_lon1 and is_lat2:
            lat_str, lon_str = coord2_str, coord1_str
        # Se a direção não for clara, podemos tentar inferir (ex: menor valor absoluto é latitude, se no Brasil)
        # Mas por agora, se não for claro, não prosseguimos com DMS
        
        if lat_str and lon_str:
            latitude_dd = dms_to_dd(lat_str, original_georref_str)
            longitude_dd = dms_to_dd(lon_str, original_georref_str)
    
    # Se o parsing DMS falhou ou não encontrou, tenta parsing de graus decimais
    if latitude_dd is None or longitude_dd is None:
        # Padrão para graus decimais: opcionalmente negativo, dígitos, ponto, dígitos
        # E.g., -23.5505, -46.6333 ou 23°33'01.8"S 46°38'00.0"W ou Lat: DD.DDDD Long: DD.DDDD
        # Este regex tenta capturar dois números decimais, potencialmente separados por vírgula, espaço ou "Lat/Lon"
        decimal_matches = re.findall(r"([+-]?\d+\.\d+)", georref_str)
        if len(decimal_matches) == 2:
            try:
                val1, val2 = float(decimal_matches[0]), float(decimal_matches[1])
                # Heurística simples para Brasil: latitude negativa, longitude negativa
                # Latitudes entre -90 e 90, longitudes entre -180 e 180
                if -90 <= val1 <= 90 and -180 <= val2 <= 180: # val1 é lat, val2 é lon
                    latitude_dd, longitude_dd = val1, val2
                elif -90 <= val2 <= 90 and -180 <= val1 <= 180: # val2 é lat, val1 é lon
                    latitude_dd, longitude_dd = val2, val1
            except ValueError:
                pass # Não conseguiu converter para float

    if latitude_dd is not None and not (-90 <= latitude_dd <= 90):
        # print(f"Debug parse_georreferencia: Latitude inválida {latitude_dd} para '{original_georref_str}'")
        latitude_dd = None
    if longitude_dd is not None and not (-180 <= longitude_dd <= 180):
        # print(f"Debug parse_georreferencia: Longitude inválida {longitude_dd} para '{original_georref_str}'")
        longitude_dd = None
        
    if latitude_dd is None or longitude_dd is None:
        return None, None # Retorna None explicitamente se não conseguiu parsear ambos

    return latitude_dd, longitude_dd
# --- Fim das funções de parsing ---

def geocode_dataframe(df_input):
    """
    Aplica geocodificação ao DataFrame.
    Prioriza 'georreferencia', depois tenta geocodificar por 'municipio' e 'uf'.
    """
    df = df_input.copy()

    # Inicializar geolocator e cache
    geolocator = Nominatim(user_agent="meu_aplicativo_consultoria_aecom_v1")
    # Aumentei o min_delay_seconds para ser mais gentil com o Nominatim
    geocode_with_delay = RateLimiter(geolocator.geocode, min_delay_seconds=1.2, error_wait_seconds=10.0, max_retries=3)
    geocode_cache = {}

    df['latitude'] = np.nan
    df['longitude'] = np.nan
    df['geo_precisao'] = 'Nenhuma' # (Nenhuma, Precisa (Original), Município (Aprox.), Falha na Geocodificação, Dados Insuficientes)

    parsed_from_georef_count = 0
    geocoded_by_municipio_count = 0
    failed_to_geocode_count = 0
    data_insufficient_count = 0

    total_rows = len(df)
    print(f"Iniciando processamento de georreferências e geocodificação para {total_rows} registros...")

    for index, row in df.iterrows():
        print(f"  Processando linha {index + 1}/{total_rows} (Processo: {row.get('numero_processo', 'N/A')})")
        
        lat, lon = parse_georreferencia(row.get('georreferencia')) # Usar .get para evitar KeyError se a coluna faltar

        if lat is not None and lon is not None:
            df.loc[index, 'latitude'] = lat
            df.loc[index, 'longitude'] = lon
            df.loc[index, 'geo_precisao'] = 'Precisa (Original)'
            parsed_from_georef_count += 1
        elif pd.notna(row.get('municipio')) and pd.notna(row.get('uf')):
            municipio_original = str(row['municipio']).strip()
            uf_original = str(row['uf']).strip()
            
            # Limpeza básica do nome do município e UF
            municipio = re.sub(r'\s*\([A-Z]{2}\)$', '', municipio_original).strip() # Remove (UF) do final do município se houver
            uf = uf_original[:2].upper() # Pega os dois primeiros caracteres da UF e capitaliza

            query = f"{municipio}, {uf}, Brasil"
            
            if query in geocode_cache and geocode_cache[query] is not None: # Checa se não é None no cache
                location = geocode_cache[query]
                # print(f"    Usando cache para: {query}")
            elif query in geocode_cache and geocode_cache[query] is None: # Já tentou e falhou
                location = None
                # print(f"    Cache indica falha anterior para: {query}")
            else:
                print(f"    Geocodificando: {query}...")
                try:
                    location = geocode_with_delay(query, timeout=15) # Aumenta timeout
                    geocode_cache[query] = location # Cacheia mesmo se for None
                except Exception as e:
                    print(f"      Erro durante geocodificação para {query}: {e}")
                    location = None
                    geocode_cache[query] = None # Cacheia a falha
            
            if location:
                df.loc[index, 'latitude'] = location.latitude
                df.loc[index, 'longitude'] = location.longitude
                df.loc[index, 'geo_precisao'] = 'Município (Aprox.)'
                geocoded_by_municipio_count += 1
            else:
                # print(f"    Falha ao geocodificar: {query}")
                df.loc[index, 'geo_precisao'] = 'Falha na Geocodificação'
                failed_to_geocode_count +=1
        else:
            df.loc[index, 'geo_precisao'] = 'Dados Insuficientes'
            data_insufficient_count +=1
            
    print("\n--- Resumo do Processamento Geo ---")
    print(f"Total de registros no arquivo: {total_rows}")
    print(f"Coordenadas obtidas da coluna 'georreferencia': {parsed_from_georef_count}")
    print(f"Coordenadas obtidas por geocodificação de Município/UF: {geocoded_by_municipio_count}")
    print(f"Falhas na geocodificação (Município/UF não encontrado ou erro Nominatim): {failed_to_geocode_count}")
    print(f"Registros com dados insuficientes para geocodificação (sem georref e sem Município/UF): {data_insufficient_count}")
    registros_sem_coords_final = total_rows - parsed_from_georef_count - geocoded_by_municipio_count
    print(f"Total de registros que ficaram sem coordenadas: {registros_sem_coords_final}")
    
    return df

if __name__ == "__main__":
    start_time = time.time()

    input_excel_path = 'docs/respostas_danos_ambientais_df_completo.xlsx'
    output_excel_path = 'docs/results_geocoded.xlsx'

    # Cria o diretório 'docs' se não existir
    os.makedirs('docs', exist_ok=True)

    print(f"Carregando dados de: {input_excel_path}")
    try:
        df_original = pd.read_excel(input_excel_path)
        print(f"Dados carregados. {len(df_original)} linhas encontradas.")
    except FileNotFoundError:
        print(f"ERRO: O arquivo de entrada '{input_excel_path}' não foi encontrado.")
        exit()
    except Exception as e:
        print(f"ERRO ao carregar o arquivo '{input_excel_path}': {e}")
        exit()

    # Garante que as colunas 'municipio', 'uf', 'georreferencia' existam, mesmo que vazias
    # para evitar KeyErrors nas funções de geocodificação.
    for col in ['municipio', 'uf', 'georreferencia']:
        if col not in df_original.columns:
            print(f"AVISO: A coluna '{col}' não existe no arquivo de entrada. Ela será criada como vazia.")
            df_original[col] = pd.NA


    df_geocoded = geocode_dataframe(df_original)

    print(f"\nSalvando dados geocodificados em: {output_excel_path}")
    try:
        df_geocoded.to_excel(output_excel_path, index=False)
        print("Arquivo salvo com sucesso!")
    except Exception as e:
        print(f"ERRO ao salvar o arquivo '{output_excel_path}': {e}")

    end_time = time.time()
    print(f"\nTempo total de processamento: {end_time - start_time:.2f} segundos.")