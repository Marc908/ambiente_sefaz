import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from lxml import etree
import uvicorn
from datetime import datetime

app = FastAPI(title="API Ambiente SEFAZ - Nacional + Estadual (real)")

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
    """Consulta SOAP real na SEFAZ."""
    inicio = datetime.now()
    try:
        body = SOAP_BODY_TEMPLATE.format(cUF=uf_code)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "nfeStatusServicoNF"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=body.encode("utf-8"), headers=headers)
            duracao = (datetime.now() - inicio).total_seconds()

            if response.status_code != 200:
                raise HTTPException(status_code=503, detail="Falha ao consultar SEFAZ")

            xml_root = etree.fromstring(response.content)

            def get_val(tag):
                elem = xml_root.xpath(f"//*[local-name()='{tag}']")
                return elem[0].text if elem else None

            return {
                "codigo_retorno": get_val("cStat"),
                "motivo": get_val("xMotivo"),
                "data_recebimento": get_val("dhRecbto"),
                "versao": get_val("versao"),
                "ambiente_retorno": get_val("tpAmb"),
                "ultima_consulta": datetime.now().isoformat(),
                "latencia_segundos": duracao
            }

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro na consulta SEFAZ: {str(e)}")

async def consultar_status(uf: str, ambiente: str):
    """Consulta estadual e nacional (apenas dados reais)."""
    uf_code = UF_CODES.get(uf)
    if not uf_code:
        raise HTTPException(status_code=400, detail="UF inválida")

    url_estadual = SEFAZ_UF_URLS.get(uf)
    url_nacional = NACIONAL_URL

    if not url_estadual:
        raise HTTPException(status_code=400, detail=f"UF {uf} não tem URL configurada")

    # consultas reais
    result_estadual = await consultar_status_real(url_estadual, uf_code)
    result_nacional = await consultar_status_real(url_nacional, uf_code)

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
