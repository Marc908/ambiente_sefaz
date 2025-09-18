import json
import httpx
from bs4 import BeautifulSoup
from pathlib import Path

URL_PORTAL = "https://www.nfe.fazenda.gov.br/portal/WebServices.aspx"
CONFIG_FILE = Path("sefaz_urls.json")

def carregar_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def atualizar_endpoints():
    print("🔍 Buscando endpoints no Portal Nacional...")
    try:
        resp = httpx.get(URL_PORTAL, timeout=15.0)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Erro ao acessar portal: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    tabelas = soup.find_all("table")

    config = carregar_config()

    for tabela in tabelas:
        linhas = tabela.find_all("tr")
        for linha in linhas:
            colunas = linha.find_all("td")
            if len(colunas) >= 3:
                uf = colunas[0].get_text(strip=True)
                servico = colunas[1].get_text(strip=True)
                url = colunas[2].get_text(strip=True)

                if "Status" in servico and url.startswith("http"):
                    if uf not in config:
                        config[uf] = {}
                    ambiente = "producao" if "homolog" not in url.lower() else "homologacao"
                    config[uf][ambiente] = url

    salvar_config(config)
    print("✅ Endpoints atualizados com sucesso!")
    return config

if __name__ == "__main__":
    atualizar_endpoints()
