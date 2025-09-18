import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from lxml import etree
import uvicorn
from datetime import datetime

app = FastAPI(title="API Ambiente SEFAZ - Nacional + Estadual com Atualização Automática")

# Arquivo com as URLs
URLS_FILE = "sefaz_urls.json"

# URLs oficiais do Nacional (sempre a mesma)
NACIONAL_URL = "https://www.nfe.fazenda.gov.br/NFeStatusServico/NFeStatusServico4.asmx"

# Dicionário base de códigos UF
UF_CODES = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17"
}

SOAP_BODY_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <nfeStatusServicoNF xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NfeStatusServico4">
      <nfeCabecMsg>
        <cUF>{cUF}</cUF>
        <versaoDados>4.00</versaoDados>
      </nfeCabecMsg>
    </nfeStatusServicoNF>
  </soap:Body>
</soap:Envelope>"""

class UFRequest(BaseModel):
    uf: str
    ambiente: str = "prod"  # prod ou hom

def load_urls():
    if os.path.exists(URLS_FILE):
        with open(URLS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_urls(data):
    with open(URLS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

SEFAZ_UF_URLS = load_urls()

async def atualizar_url(uf: str, url_antiga: str):
    """
    Simulação: aqui você pode colocar scraping ou uma API que mantém as URLs atualizadas.
    Por enquanto, só marca como indisponível.
    """
    print(f"[Updater] Tentando atualizar URL da UF {uf}...")
    nova_url = url_antiga.replace("NfeStatusServico2", "NfeStatusServico4")  # exemplo simples
    SEFAZ_UF_URLS[uf] = nova_url
    save_urls(SEFAZ_UF_URLS)
    return nova_url

async def consultar_status_real(url: str, uf_code: str, uf: str):
    try:
        body = SOAP_BODY_TEMPLATE.format(cUF=uf_code)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "nfeStatusServicoNF"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, data=body.encode("utf-8"), headers=headers)
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")
            xml_root = etree.fromstring(response.content)
            xMotivo_elem = xml_root.xpath("//*[local-name()='xMotivo']")
            dhRecbto_elem = xml_root.xpath("//*[local-name()='dhRecbto']")
            motivo = xMotivo_elem[0].text if xMotivo_elem else "Sem motivo informado"
            data = dhRecbto_elem[0].text if dhRecbto_elem else datetime.utcnow().isoformat()
            disponivel = "disponivel" in motivo.lower() or "em operacao" in motivo.lower()
            return {"disponivel": disponivel, "motivo": motivo, "ultima_consulta": data}
    except Exception as e:
        # Se falhar, tenta atualizar URL automaticamente
        print(f"[Erro] {uf}: {str(e)}")
        if url and "NfeStatusServico2" in url:
            nova_url = await atualizar_url(uf, url)
            return await consultar_status_real(nova_url, uf_code, uf)
        return {"disponivel": False, "motivo": f"Falha ao consultar SEFAZ: {str(e)}", "ultima_consulta": datetime.utcnow().isoformat()}

async def consultar_status(uf: str, ambiente: str):
    uf_code = UF_CODES.get(uf)
    if not uf_code:
        raise HTTPException(status_code=400, detail="UF inválida")

    url_estadual = SEFAZ_UF_URLS.get(uf)
    if not url_estadual:
        raise HTTPException(status_code=400, detail=f"UF {uf} não tem URL configurada")

    # estadual
    result_estadual = await consultar_status_real(url_estadual, uf_code, uf)

    # nacional
    result_nacional = await consultar_status_real(NACIONAL_URL, uf_code, uf)

    return {
        "uf": uf,
        "ambiente": ambiente,
        "status_estadual": result_estadual,
        "status_nacional": result_nacional
    }

@app.post("/sefaz/status")
async def status_post(req: UFRequest):
    return await consultar_status(req.uf.upper(), req.ambiente)

@app.get("/sefaz/status")
async def status_get(uf: str, ambiente: str = "prod"):
    return await consultar_status(uf.upper(), ambiente)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8081))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
