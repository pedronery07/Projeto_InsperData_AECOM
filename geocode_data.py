import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import numpy as np
import re
import time  # Para medir o tempo
import os    # Para criar o diretório 'docs'

# --- Funções de parsing de DMS (inalteradas) ---
def dms_to_dd(dms_str, original_full_ref=""):
    if pd.isna(dms_str) or not isinstance(dms_str, str) or dms_str.strip().upper() == 'NULL' or dms_str.strip() == "":
        return None
    dms_str = dms_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’")
    dms_str = dms_str.replace("`", "’")
    match = re.search(r"(\d+)\s*(?:°|º|DEG|GRAUS|\s)\s*(\d+)\s*(?:’|'|MIN|\s)\s*([\d\.,]+)\s*(?:”|\"|SEC|\s)\s*([NSEWLO])",
                      dms_str, re.IGNORECASE)
    if not match:
        match_simple = re.search(r"(\d+)\s*(?:°|º|DEG|GRAUS)\s*([\d\.,]+)\s*(?:’|'|MIN)\s*([NSEWLO])",
                                   dms_str, re.IGNORECASE)
        if match_simple:
            degrees, minutes, direction = match_simple.groups()
            seconds = "0"
        else:
            return None
    else:
        degrees, minutes, seconds, direction = match.groups()
    try:
        seconds = seconds.replace(',', '.')
        minutes = minutes.replace(',', '.')
        dd = float(degrees) + float(minutes)/60 + float(seconds)/(3600)
    except ValueError:
        return None
    direction = direction.upper()
    if direction in ['S', 'O', 'W']:
        dd *= -1
    elif direction not in ['N', 'E', 'L']:
        return None
    return dd


def parse_georreferencia(georref_str):
    if pd.isna(georref_str) or not isinstance(georref_str, str) or georref_str.strip().upper() == 'NULL' or georref_str.strip() == "":
        return None, None
    georref_str = georref_str.strip()
    georref_str = georref_str.replace("‘", "’").replace("“", "”").replace("''", "”").replace("'", "’").replace("`", "’")
    dms_pattern = r"\d+\s*(?:°|º|DEG|GRAUS|\s)\s*\d+\s*(?:’|'|MIN|\s)\s*[\d\.,]+\s*(?:”|\"|SEC|\s)\s*[NSEWLO]"
    simple_pattern = r"\d+\s*(?:°|º|DEG|GRAUS)\s*[\d\.,]+\s*(?:’|'|MIN)\s*[NSEWLO]"
    coords = list(re.finditer(dms_pattern, georref_str, re.IGNORECASE))
    if len(coords) < 2:
        coords = list(re.finditer(simple_pattern, georref_str, re.IGNORECASE))
    lat_dd, lon_dd = None, None
    if len(coords) == 2:
        c1, c2 = coords[0].group(0), coords[1].group(0)
        lat_str, lon_str = None, None
        if re.search(r"[NS]$", c1, re.IGNORECASE) and re.search(r"[EWLO]$", c2, re.IGNORECASE):
            lat_str, lon_str = c1, c2
        elif re.search(r"[EWLO]$", c1, re.IGNORECASE) and re.search(r"[NS]$", c2, re.IGNORECASE):
            lat_str, lon_str = c2, c1
        if lat_str and lon_str:
            lat_dd = dms_to_dd(lat_str, georref_str)
            lon_dd = dms_to_dd(lon_str, georref_str)
    if lat_dd is None or lon_dd is None:
        decs = re.findall(r"([+-]?\d+\.\d+)", georref_str)
        if len(decs) == 2:
            try:
                v1, v2 = float(decs[0]), float(decs[1])
                if -90 <= v1 <= 90 and -180 <= v2 <= 180:
                    lat_dd, lon_dd = v1, v2
                elif -90 <= v2 <= 90 and -180 <= v1 <= 180:
                    lat_dd, lon_dd = v2, v1
            except ValueError:
                pass
    if lat_dd is not None and not (-90 <= lat_dd <= 90): lat_dd = None
    if lon_dd is not None and not (-180 <= lon_dd <= 180): lon_dd = None
    if lat_dd is None or lon_dd is None:
        return None, None
    return lat_dd, lon_dd

# --- Função principal de geocodificação ---
def geocode_dataframe(df_input):
    df = df_input.copy()
    geolocator = Nominatim(user_agent="meu_aplicativo_consultoria_v2")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2, error_wait_seconds=10.0, max_retries=3)
    geocode_cache = {}

    parsed_from_georef_count = 0
    geocoded_by_municipio_count = 0
    geocoded_by_regiao_count = 0
    failed_to_geocode_count = 0
    data_insufficient_count = 0

    df['latitude'] = np.nan
    df['longitude'] = np.nan
    df['geo_precisao'] = 'Nenhuma'

    total = len(df)
    print(f"Iniciando geocodificação de {total} registros...")

    for idx, row in df.iterrows():
        print(f" Processando {idx+1}/{total} (Processo: {row.get('numero_processo','N/A')})... Fonte: {row.get('fonte_dados')}")
        lat, lon = parse_georreferencia(row.get('georreferencia'))
        if lat is not None and lon is not None:
            df.at[idx, 'latitude'] = lat
            df.at[idx, 'longitude'] = lon
            df.at[idx, 'geo_precisao'] = 'Precisa (Original)'
            parsed_from_georef_count += 1
            continue

        fonte = str(row.get('fonte_dados', '')).strip().lower()
        # IOPC: geocode via 'regiao'
        if fonte == 'iopc':
            region = row.get('regiao')
            if pd.notna(region) and isinstance(region, str) and region.strip():
                query = region.strip()
                loc = geocode_cache.get(query)
                if loc is None and query not in geocode_cache:
                    print(f"  Geocodificando região: {query}")
                    try:
                        loc = geocode(query, timeout=15)
                    except Exception as e:
                        print(f"    Erro geocodificação região '{query}': {e}")
                        loc = None
                    geocode_cache[query] = loc
                if loc:
                    df.at[idx, 'latitude'] = loc.latitude
                    df.at[idx, 'longitude'] = loc.longitude
                    df.at[idx, 'geo_precisao'] = 'Região (Aprox.)'
                    geocoded_by_regiao_count += 1
                else:
                    df.at[idx, 'geo_precisao'] = 'Falha na Geocodificação'
                    failed_to_geocode_count += 1
            else:
                df.at[idx, 'geo_precisao'] = 'Dados Insuficientes'
                data_insufficient_count += 1
            continue

        # JusBrasil e Juscraper: geocode via município/UF
        if pd.notna(row.get('municipio')) and pd.notna(row.get('uf')):
            mun = str(row['municipio']).strip()
            uf = str(row['uf']).strip()[:2].upper()
            query = f"{mun}, {uf}, Brasil"
            loc = geocode_cache.get(query)
            if loc is None and query not in geocode_cache:
                print(f"  Geocodificando município: {query}")
                try:
                    loc = geocode(query, timeout=15)
                except Exception as e:
                    print(f"    Erro geocodificação município '{query}': {e}")
                    loc = None
                geocode_cache[query] = loc
            if loc:
                df.at[idx, 'latitude'] = loc.latitude
                df.at[idx, 'longitude'] = loc.longitude
                df.at[idx, 'geo_precisao'] = 'Município (Aprox.)'
                geocoded_by_municipio_count += 1
            else:
                df.at[idx, 'geo_precisao'] = 'Falha na Geocodificação'
                failed_to_geocode_count += 1
        else:
            df.at[idx, 'geo_precisao'] = 'Dados Insuficientes'
            data_insufficient_count += 1

    # Resumo
    print("\n--- Resumo do Processamento Geo ---")
    print(f"Total de registros: {total}")
    print(f"Da coluna georreferencia: {parsed_from_georef_count}")
    print(f"Via Região (IOPC): {geocoded_by_regiao_count}")
    print(f"Via Município/UF: {geocoded_by_municipio_count}")
    print(f"Falhas na geocodificação: {failed_to_geocode_count}")
    print(f"Dados insuficientes: {data_insufficient_count}")
    sem_coords = total - parsed_from_georef_count - geocoded_by_regiao_count - geocoded_by_municipio_count
    print(f"Sem coordenadas no final: {sem_coords}")
    return df


if __name__ == "__main__":
    start = time.time()
    input_path = 'docs\df_jusbrasil_iopc_juscraper.xlsx'
    output_path = 'docs/results_geocoded.xlsx'
    os.makedirs('docs', exist_ok=True)
    print(f"Carregando dados de: {input_path}")
    try:
        df_original = pd.read_excel(input_path)
        print(f"Linhas carregadas: {len(df_original)}")
    except FileNotFoundError:
        print(f"ERRO: '{input_path}' não encontrado.")
        exit(1)
    except Exception as e:
        print(f"ERRO ao ler '{input_path}': {e}")
        exit(1)

    # Garante existência de colunas
    for col in ['municipio', 'uf', 'georreferencia', 'fonte_dados', 'regiao']:
        if col not in df_original.columns:
            print(f"AVISO: coluna '{col}' ausente. Criando vazia.")
            df_original[col] = pd.NA

    df_geocoded = geocode_dataframe(df_original)

    print(f"\nSalvando em: {output_path}")
    try:
        df_geocoded.to_excel(output_path, index=False)
        print("Salvo com sucesso!")
    except Exception as e:
        print(f"ERRO ao salvar '{output_path}': {e}")
    end = time.time()
    print(f"Tempo total: {end - start:.2f}s")
