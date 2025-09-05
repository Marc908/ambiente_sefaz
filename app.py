import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from lxml import etree
import httpx
import uvicorn

app = FastAPI(title="API Blindada SEFAZ")

# Estrutura de URLs por UF e Ambiente
SEFAZ_UF_URLS = {
    "SP": {
        "prod": "https://nfe.sefaz.sp.gov.br/nfeweb/services/NfeStatusServico2.asmx",
        "hml": "https://homologacao.nfe.sefaz.sp.gov.br/nfeweb/services/NfeStatusServico2.asmx"
    },
    "RJ": {
        "prod": "https://nfe.sefaz.rj.gov.br/nfeweb/services/NfeStatusServico2.asmx",
        "hml": "https://homologacao.nfe.sefaz.rj.gov.br/nfeweb/services/NfeStatusServico2.asmx"
    },
    # Adicione todas as UFs restantes da mesma forma
}

NACIONAL_URLS = {
    "prod": "https://www.nfe.fazenda.gov.br/NFeStatusServico/NFeStatusServico2.asmx",
    "hml": "https://homologacao.nfe.fazenda.gov.br/NFeStatusServico/NFeStatusServico2.asmx"
}

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
    <nfeStatusServicoNF xmlns="http://www.portalfiscal.inf.br/nfe">
      <nFeCabecMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NfeStatusServico2">
        <cUF>{cUF}</cUF>
        <versaoDados>4.00</versaoDados>
      </nFeCabecMsg>
    </nfeStatusServicoNF>
  </soap:Body>
</soap:Envelope>"""

# Cache interno para endpoints ativos
active_url_cache = {}

async def validar_endpoint(url: str) -> bool:
    """Checa se a URL está acessível"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.head(url)
            return r.status_code == 200
    except:
        return False

async def consultar_status_soap(url: str, uf_code: str):
    """Consulta SOAP e retorna status"""
    body = SOAP_BODY_TEMPLATE.format(cUF=uf_code)
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "nfeStatusServicoNF"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=body.encode('utf-8'), headers=headers)
            if response.status_code != 200:
                return {"disponivel": False, "motivo": f"HTTP {response.status_code}"}
            xml_root = etree.fromstring(response.content)
            ns = {
                'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
                'nfe': 'http://www.portalfiscal.inf.br/nfe/wsdl/NfeStatusServico2'
            }
            xMotivo_elem = xml_root.xpath('//nfe:xMotivo', namespaces=ns)
            if xMotivo_elem:
                motivo = xMotivo_elem[0].text
                disponivel = "disponivel" in motivo.lower() or "em operacao" in motivo.lower()
                return {"disponivel": disponivel, "motivo": motivo}
            return {"disponivel": False, "motivo": "Resposta inválida da SEFAZ"}
    except Exception as e:
        return {"disponivel": False, "motivo": str(e)}

async def get_active_url(uf: str, ambiente: str):
    """Retorna URL ativa ou fallback"""
    key = f"{uf}_{ambiente}"
    if key in active_url_cache:
        return active_url_cache[key]

    url = SEFAZ_UF_URLS.get(uf, {}).get(ambiente)
    if url and await validar_endpoint(url):
        active_url_cache[key] = url
        return url
    # Fallback nacional
    url_nac = NACIONAL_URLS.get(ambiente)
    if await validar_endpoint(url_nac):
        active_url_cache[key] = url_nac
        return url_nac
    return None

# Modelo POST
class StatusRequest(BaseModel):
    uf: str
    ambiente: str = "prod"

@app.get("/sefaz/status")
async def status_sefaz_get(uf: str, ambiente: str = "prod"):
    uf = uf.upper()
    ambiente = ambiente.lower()
    if uf not in UF_CODES:
        raise HTTPException(status_code=400, detail="UF inválida")
    if ambiente not in ["prod", "hml"]:
        raise HTTPException(status_code=400, detail="Ambiente inválido")

    url = await get_active_url(uf, ambiente)
    if not url:
        return {"uf": uf, "ambiente": ambiente, "disponivel": False, "motivo": "Nenhum endpoint ativo"}

    status = await consultar_status_soap(url, UF_CODES[uf])
    return {"uf": uf, "ambiente": ambiente, "status": status}

@app.post("/sefaz/status")
async def status_sefaz_post(req: StatusRequest):
    uf = req.uf.upper()
    ambiente = req.ambiente.lower()
    if uf not in UF_CODES:
        raise HTTPException(status_code=400, detail="UF inválida")
    if ambiente not in ["prod", "hml"]:
        raise HTTPException(status_code=400, detail="Ambiente inválido")

    url = await get_active_url(uf, ambiente)
    if not url:
        return {"uf": uf, "ambiente": ambiente, "disponivel": False, "motivo": "Nenhum endpoint ativo"}

    status = await consultar_status_soap(url, UF_CODES[uf])
    return {"uf": uf, "ambiente": ambiente, "status": status}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8081))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
