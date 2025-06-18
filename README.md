# Projeto_InsperData_AECOM
Repositório do projeto de valoração de danos ambientais entre Insper Data e AECOM. 

### Setup

Para utilizar o código deste repositório, siga as instruções a seguir:

Crie um ambiente virtual do Python:

``` shell
python -m venv env
```

Ative o ambiente virtual:

``` shell
env\Scripts\activate
```

Instale as dependências com:

``` shell
pip install -r requirements.txt --upgrade
```

Para gerar uma chave de API, acesse o link do GEMINI a seguir:

https://aistudio.google.com/app/apikey

Após gerada a chave de API, inclua-a em novo arquivo nomeado '.env' com o seguinte formato:

``` shell
GEMINI_API_KEY_X = 'INSIRA SUA CHAVE AQUI'
```

Sendo X um número da chave. O código atual prevê o uso de até 4 chaves. Caso necessite utilizar mais chaves, é necessário alteração no código.

