import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from lxml import etree
import uvicorn

app = FastAPI(title="API Ambiente SEFAZ - Mock + Nacional")

SEFAZ_UF_URLS = {
    "SP": "https://nfe.sefaz.sp.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RJ": "https://nfe.sefaz.rj.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "MG": "https://nfe.sefaz.mg.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    # adicione outras UFs aqui
}

NACIONAL_URL = "https://www.nfe.fazenda.gov.br/NFeStatusServico/NFeStatusServico2.asmx"

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
    ambiente: str = "prod"  # prod ou hom

async def consultar_status_real(url: str, uf_code: str):
    """Consulta SOAP real na SEFAZ (pode falhar)."""
    try:
        body = SOAP_BODY_TEMPLATE.format(cUF=uf_code)
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "nfeStatusServicoNF"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=body.encode("utf-8"), headers=headers)
            if response.status_code != 200:
                return None
            xml_root = etree.fromstring(response.content)
            xMotivo_elem = xml_root.xpath("//*[local-name()='xMotivo']")
            if xMotivo_elem:
                motivo = xMotivo_elem[0].text
                disponivel = "disponivel" in motivo.lower() or "em operacao" in motivo.lower()
                return {"disponivel": disponivel, "motivo": motivo}
        return None
    except Exception:
        return None

async def consultar_status(uf: str, ambiente: str):
    """Consulta estadual e nacional, com fallback mock."""
    uf_code = UF_CODES.get(uf)
    if not uf_code:
        raise HTTPException(status_code=400, detail="UF inválida")

    url_estadual = SEFAZ_UF_URLS.get(uf)
    url_nacional = NACIONAL_URL

    # estadual
    result_estadual = None
    if url_estadual:
        result_estadual = await consultar_status_real(url_estadual, uf_code)
    if not result_estadual:
        result_estadual = {
            "disponivel": True,
            "motivo": "Mock: serviço estadual simulado como disponível"
        }

    # nacional
    result_nacional = await consultar_status_real(url_nacional, uf_code)
    if not result_nacional:
        result_nacional = {
            "disponivel": True,
            "motivo": "Mock: serviço nacional simulado como disponível"
        }

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
