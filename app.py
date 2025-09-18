import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from lxml import etree
import uvicorn
from pathlib import Path
from datetime import datetime

app = FastAPI(title="API Ambiente SEFAZ - Nacional + Estadual")

CONFIG_FILE = Path("sefaz_urls.json")

# Códigos das UFs
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

class UFRequest(BaseModel):
    uf: str
    ambiente: str = "producao"  # producao ou homologacao

def carregar_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

async def consultar_status_real(url: str, uf_code: str):
    """Consulta SOAP real na SEFAZ (sem mock)."""
    try:
        body = SOAP_BODY_TEMPLATE.format(cUF=uf_code)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "nfeStatusServicoNF"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=body.encode("utf-8"), headers=headers)
            if response.status_code != 200:
                return None
            xml_root = etree.fromstring(response.content)
            motivo_elem = xml_root.xpath("//*[local-name()='xMotivo']")
            cstat_elem = xml_root.xpath("//*[local-name()='cStat']")
            if motivo_elem:
                motivo = motivo_elem[0].text
                cstat = cstat_elem[0].text if cstat_elem else "000"
                disponivel = cstat == "107"
                return {
                    "disponivel": disponivel,
                    "codigo": cstat,
                    "motivo": motivo,
                    "ultima_consulta": datetime.now().isoformat()
                }
        return None
    except Exception as e:
        return {"erro": str(e), "disponivel": False}

async def consultar_status(uf: str, ambiente: str):
    """Consulta estadual e nacional com base no JSON atualizado."""
    uf_code = UF_CODES.get(uf)
    if not uf_code:
        raise HTTPException(status_code=400, detail="UF inválida")

    config = carregar_config()
    urls = config.get(uf)
    if not urls or ambiente not in urls:
        raise HTTPException(status_code=400, detail=f"UF {uf} não tem URL configurada para {ambiente}")

    url_estadual = urls[ambiente]
    url_nacional = config.get("NACIONAL", {}).get(ambiente)

    result_estadual = await consultar_status_real(url_estadual, uf_code)
    result_nacional = await consultar_status_real(url_nacional, uf_code) if url_nacional else None

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
async def status_get(uf: str, ambiente: str = "producao"):
    return await consultar_status(uf.upper(), ambiente)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8081))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
