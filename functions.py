import time
from pydantic import BaseModel
import os
from google import genai
import json

# Classe usada para retornar uma resposta padrão em caso de falha
class FailResponse:
    def __init__(self, data: dict):
        self.text = json.dumps(data) # Converte o dicionário em uma string JSON

# Função principal que verifica se o texto contém um dano ambiental
def verifica_dano_ambiental(texto):
    """
    Função que verifica se o texto possui dano ambiental.
    Se houver, justifica a resposta. Caso contrário, responde "Não há dano ambiental".
    """
    # Prompt que será enviado ao modelo de linguagem para avaliação do texto

    prompt = f"""
    Você é um especialista em direito ambiental.
    Analise o texto abaixo e verifique exclusivamente se ele descreve um dano ao meio ambiente.

    Dano ambiental, para fins desta análise, é qualquer impacto negativo ao meio ambiente natural — incluindo água, solo, ar, fauna, flora ou paisagem — causado por ação ou omissão humana.

    Ignore qualquer outro tipo de dano (como material, moral/ao consumidor ou patrimonial). Não considere fundamentos jurídicos fora do conceito de dano ambiental.

    Importante: classifique como dano ambiental apenas se houver evidências claras de impacto negativo ao meio ambiente natural. Não considere danos indiretos ou potenciais, apenas danos efetivos e diretos.

    Alguns exemplos de danos ambientais incluem:
    - Desmatamento ilegal de áreas protegidas
    - Contaminação de corpos d'água por produtos químicos
    - Poluição do ar por emissões industriais
    - Destruição de habitats naturais
    - Derramamento de óleo em ecossistemas aquáticos
    Não considere como dano ambiental:
    - Danos materiais a propriedades privadas sem relação direta ou indireta com o meio ambiente
    - Danos morais a indivíduos ou comunidades sem relação direta ou indireta com o meio ambiente 
    - Questões de responsabilidade civil sem relação direta ou indireta com o meio ambiente
    - Questões de direito do consumidor sem relação direta ou indireta com o meio ambiente
    - Questões patrimoniais sem relação direta ou indireta com o meio ambiente

    Se houver dano ambiental, responda com uma justificativa de no máximo 20 palavras. Caso contrário, responda apenas: "Não há dano ambiental".

    Texto: {texto}
    """
    
    # Define o formato esperado da resposta vinda do modelo (como um esquema JSON)
    class FormatoResposta(BaseModel):
        isDanoAmbiental: bool
        justificativa: str

    # Função auxiliar que faz a requisição para o modelo Gemini usando a chave especificada
    def requisicao_gemini(key):
        client = genai.Client(api_key=os.getenv(key))
        response = client.models.generate_content(
            model="gemini-2.0-flash", #modelo utilzado
            contents=prompt, #prompt criado acima
            config={
                "response_mime_type": "application/json", # Formato da resposta esperada
                'response_schema': FormatoResposta,       # Validação da estrutura da resposta
                'temperature': 1.0                        # Grau de aleatoriedade da resposta
                # 'max_output_tokens': 500,
            }
        )
        time.sleep(2)
        return response

    # Lista de chaves para tentativa sequencial, caso alguma falhe
    chaves = ['GEMINI_API_KEY', 'GEMINI_API_KEY_2', 'GEMINI_API_KEY_3', 'GEMINI_API_KEY_4', 'GEMINI_API_KEY_5']

    # Tenta usar cada chave para fazer a requisição até obter uma resposta válida
    for chave in chaves:
        try:
            resposta = requisicao_gemini(chave)
            return resposta # Se funcionar, retorna imediatamente
        except Exception as e:
            # Se houver erro, espera um pouco e tenta com a próxima chave
            # print(f"Erro com chave {chave}: {e}")
            time.sleep(5)
            continue

    # Se todas as tentativas falharem, retorna uma resposta padrão com erro
    fallback_data = {
        "isDanoAmbiental": False,
        "justificativa": "Erro na classificação automática"
    }

    return FailResponse(fallback_data)

def analisa_sentenca(texto_extraido):
    """
    Função que extrai informações de um texto judicial relacionado a danos ambientais.
    O texto deve ser um texto bruto que descreve um processo judicial relacionado a algum dano ambiental.
    """
    # Cria um prompt longo e detalhado para instruir o modelo de IA sobre como extrair dados estruturados do texto judicial.
    prompt = f"""
        SYSTEM: Você é meu assistente especialista em análise e extração de elementos de textos judiciais. Você irá realizar extrações especificamente sobre
        danos socioambientais de diversos tipos, pensando em futuramente usar a tabela gerada para fazer uma modelagem preditiva de multas para danos socioambientais.

        INSTRUCTIONS:
        Você receberá um texto bruto que descreve um processo judicial relacionado a algum dano ambiental.
        Seu objetivo é analisar esse texto e extrair 15 informações específicas para montar um banco de dados, conforme as instruções abaixo.
        Definição útil: Dano ambiental é qualquer prejuízo causado ao meio ambiente (água, solo, ar, fauna, flora, patrimônio paisagístico etc.) por ação ou omissão
        de um terceiro, sendo gerador de obrigação de reparação, conforme os artigos 186 e 927 do Código Civil.
        Retorno esperado:

        [0] Número do processo judicial no formato "0000000-00.0000.0.00.0000"
         Se não houver, retorne: NULL
        
        [1] Georreferência do local afetado, no formato: XX°xx’xx.xx” S e XX°xx’xx.xx” O
         Se não houver, retorne: NULL

        [2] Sigla da Unidade Federativa (UF) (ex: "SP", "MG" etc.)
         Se não houver, retorne: NULL

        [3] Município ou cidade do local afetado. (ex: "São Paulo", "Minas Gerais" etc)
         Se não houver, retorne: NULL

        [4] Nome do responsável pelo dano ambiental (empresa ou pessoa física).
         Se não houver, retorne: NULL

        [5] Categoria do responsável: "Pessoa Física" ou "Pessoa Jurídica"
         Se não houver, retorne: NULL

        [6] Tipo de impacto: Categoria do dano (ex.: "Desmatamento de APP", "Derramamento de Petróleo", "Poluição Hídrica").
        Se não houver, retorne: NULL

        [7] Descrição do impacto: Resuma o impacto em até 30 palavras.
        Se não houver, retorne: NULL

        [8] Data do impacto ambiental no formato: DD/MM/AA
         Se não houver, retorne: NULL

        [9] Extensão da área afetada (ex: "15000".)
         Se não houver, retorne: NULL
        Sempre em metros quadrados (m²) ou hectares (ha), então converta se necessário. Não use separadores para milhares

        [10] Unidade de medida da área (ex: "ha" ou "m2")
         Se não houver, retorne: NULL

        [11] Houve compensação não monetária atribuída (ou seja, alguma ação de reparação ambiental, como reflorestamento, recuperação de áreas degradadas, etc.)
         Se houver, retorne: "True"
         Se não houver, retorne: "False"

        [12] Categoria da compensação: "Multas Administrativas", "Compensações Financeiras", "Obrigações de Fazer (com custo)", "Custas Judiciais e Acordos" ou "Valoração Econômica".
         Se não houver, retorne: NULL
         Tente não fugir dessas categorias.

        [13] Tipo de multa: (0, 1 ou 2)
        Se for uma única multa aplicada sobre o responsável, coloque 0
        Se for algo como uma multa diária, coloque 1.
        Se forem os dois, como uma multa imediata e um pagamento diário, coloque 2

        [14] Valor completo da multa/ressarcimento/compensação ou qualquer outro termo similar de condenação monetária pelo dano ambiental para o Tipo 0 ou 2: (ex: "123000.00", "999999.99")
        Caso o item 12 seja 0, complete essa coluna com o valor total da multa aplicada. Inclua eventuais danos morais difusos, coletivos e materiais se houver.
        Caso o item 12 seja 1, deixe como NULL
        Caso o item 12 seja 2, complete essa coluna com o valor total da multa imediata aplicada.

        [15] Valor da multa/ressarcimento/compensação ou qualquer outro termo similar de condenação monetária pelo dano ambiental diária para o Tipo 1 ou 2: (ex: "123000.00", "10000.50")
        Caso o item 12 seja 1 ou 2, complete essa coluna com o valor diário a ser pago pelo responsável. Inclua eventuais danos morais difusos, coletivos e materiais se houver.
        Caso o item 12 seja 0, deixe como NULL

        IMPORTANTE: A string será usada para um dataframe posteriormente. Logo:
        NÃO inclua explicações, formatações extras, aspas ou colchetes na resposta.
        NÃO deixe nenhuma casa em branco ou vazia. SEMPRE coloque NULL caso não encontre no texto.
        NÃO inclua o texto original, nem explicações, apenas a string limpa.
        A ordem dos elementos PRECISA SER RESPEITADA!! NENHUM ELEMENTO PODE VIR ANTES DA SUA POSIÇÃO!!

        USER:
        Texto para análise:
        {texto_extraido}
    """
    
    # Define a estrutura esperada da resposta do modelo, usando o pydantic BaseModel.
    # Isso permite validar e estruturar a resposta JSON automaticamente.
    class FormatoResposta2(BaseModel):
        numero_processo: str
        georreferencia: str
        uf: str
        municipio: str
        responsavel: str
        categoria_responsavel: str
        tipo_impacto: str
        descricao_impacto: str
        data_impacto: str
        area_afetada: str
        unidade_area: str
        houve_compensacao: bool
        categoria_compensacao: str
        tipo_multa: int | str
        valor_multa: float | str
        valor_multa_diaria: float | str

    # Função auxiliar para enviar o prompt ao modelo Gemini via API.
    def requisicao_gemini(key):
        client = genai.Client(api_key=os.getenv(key))
        response = client.models.generate_content(
            model="gemini-2.0-flash", # modelo utilizado
            contents=prompt, # prompt criado acima
            config={
                "response_mime_type": "application/json", # Formato da resposta esperada
                'response_schema': FormatoResposta2,       # Validação da estrutura da resposta
                'temperature': 1.0    ,                        # Grau de aleatoriedade da resposta
                # 'max_output_tokens': 500,
            }
        )
        time.sleep(2)
        return response

    # Lista de chaves de API a serem testadas em sequência caso ocorram erros (como limites de uso).
    chaves = ['GEMINI_API_KEY', 'GEMINI_API_KEY_2', 'GEMINI_API_KEY_3', 'GEMINI_API_KEY_4', 'GEMINI_API_KEY_5']
    # Tenta usar cada chave até obter uma resposta válida ou esgotar todas as opções.
    for chave in chaves:
        try:
            resposta = requisicao_gemini(chave)
            return resposta # Retorna a primeira resposta válida recebida
        except Exception as e:
            # Se ocorrer um erro, espera um pouco e tenta com a próxima chave
            # print(f"Erro com chave {chave}: {e}")
            time.sleep(5)
            continue
    
    # Caso todas as requisições falhem, retorna uma resposta padrão indicando erro em todos os campos.
    fallback_data = {
        "numero_processo" : "Erro na classificação automática",
        "georreferencia" : "Erro na classificação automática",
        "uf" : "Erro na classificação automática",
        "municipio" : "Erro na classificação automática",
        "responsavel" : "Erro na classificação automática",
        "categoria_responsavel" : "Erro na classificação automática",
        "tipo_impacto" : "Erro na classificação automática",
        "descricao_impacto" : "Erro na classificação automática",
        "data_impacto" : "Erro na classificação automática",
        "area_afetada" : "Erro na classificação automática",
        "unidade_area" : "Erro na classificação automática",
        "houve_compensacao" : "Erro na classificação automática",
        "categoria_compensacao" : "Erro na classificação automática",
        "tipo_multa" : "Erro na classificação automática",
        "valor_multa" : "Erro na classificação automática",
        "valor_multa_diaria" : "Erro na classificação automática"
    }

    return FailResponse(fallback_data)

def divide_lista_em_partes(lista, num_partes):
    # Divisão exata: a lista pode ser dividida igualmente sem sobras.
    if len(lista) % num_partes == 0:
        # Dvisão exata
        tamanho_parte = len(lista) // num_partes
        # Cria uma lista de sublistas (partes) com tamanho igual.
        partes = [lista[i:i + tamanho_parte] for i in range(0, len(lista), tamanho_parte)]
    else:
        # Divisão com sobra: o tamanho da lista não é múltiplo do número de partes.
        # Coloca o resto na última parte
        tamanho_parte = len(lista) // num_partes
        partes = []
        for i in range(0, num_partes):
            if i == num_partes - 1:
                # A última parte recebe todos os elementos restantes.
                partes.append(lista[i * tamanho_parte:])
            else:
                # As partes anteriores recebem exatamente tamanho_parte elementos.
                partes.append(lista[i * tamanho_parte:(i + 1) * tamanho_parte])
    return partes

def analisa_tipo(tipo_impacto):
        # Prompt que será enviado ao modelo de linguagem para categorização do tipo de impacto ambiental.
        prompt = f"""
        SYSTEM: Você é um especialista em meio ambiente e direito ambiental.

        INSTRUCTION: Sua tarefa é analisar o tipo de impacto específico fornecido e classificá-lo dentro de apenas uma das categorias generalizadas listadas a seguir. 
        Considere que cada tipo de impacto pode ser classificado em apenas uma categoria. 
        Em caso de um valor NULL, também devolva NULL. 
        Em caso de um impacto específico idêntico a uma das categorias generalizadas, apenas devolva esta mesma categoria.

        CATEGORIAS GERAIS: 
        'Poluição Hídrica',
        'Poluição do Solo',
        'Poluição do Ar e Sonora',
        'Desmatamento e Danos à Flora',
        'Incêndios e Queimadas',
        'Danos à Fauna',
        'Gestão Inadequada de Resíduos',
        'Ocupação e Construção Irregular',
        'Erosão, Assoreamento e Impactos Geológicos',
        'Extração Ilegal de Recursos Naturais',
        'Falhas e Riscos de Infraestrutura',
        'Impactos Sociais e à Saúde Pública',
        'Danos ao Patrimônio e Bens Públicos',
        'Infrações Administrativas e Legais',
        'Derramamento de Petróleo',
        'Dano Ambiental Genérico / Outros'

        USER: Aqui está o tipo de impacto que você deve generalizar: {tipo_impacto}   
        """

        # Define a estrutura esperada da resposta do modelo, usando o pydantic BaseModel.
        class FormatoResposta(BaseModel):
            categoria_generalizada: str

        def requisicao_gemini(key):
            client = genai.Client(api_key=os.getenv(key))
            response = client.models.generate_content(
                model="gemini-2.0-flash", # modelo utilizado
                contents=prompt, # prompt criado acima
                config={
                    "response_mime_type": "application/json", # Formato da resposta esperada
                    'response_schema': FormatoResposta,  # Validação da estrutura da resposta
                    'temperature': 1.0 # Grau de aleatoriedade da resposta
                    # 'max_output_tokens': 500,
                }
            )
            time.sleep(1)
            return response
        
        # Lista de chaves de API a serem testadas em sequência caso ocorram erros (como limites de uso).
        chaves = ['GEMINI_API_KEY', 'GEMINI_API_KEY_2', 'GEMINI_API_KEY_3', 'GEMINI_API_KEY_4']

        # Tenta usar cada chave até obter uma resposta válida ou esgotar todas as opções.
        for chave in chaves:
            try:
                resposta = requisicao_gemini(chave) # Retorna a primeira resposta válida recebida
                return resposta 
            except Exception as e:
                # Se ocorrer um erro, espera um pouco e tenta com a próxima chave
                # print(f"Erro com chave {chave}: {e}")
                time.sleep(5)
                continue

        # Caso todas as requisições falhem, retorna uma resposta padrão indicando erro.
        fallback_data = {
            "categoria_generalizada" : "Erro na classificação automática"
        }

        return FailResponse(fallback_data)