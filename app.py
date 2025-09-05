from fastapi import FastAPI, HTTPException
import httpx
from lxml import etree

app = FastAPI(title="API Ambiente SEFAZ")

SEFAZ_UF_URLS = {
    "AC": "https://nfe.sefaz.ac.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "AL": "https://nfe.sefaz.al.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "AP": "https://nfe.sefaz.ap.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "AM": "https://nfe.sefaz.am.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "BA": "https://nfe.sefaz.ba.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "CE": "https://nfe.sefaz.ce.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "DF": "https://nfe.sefaz.df.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "ES": "https://nfe.sefaz.es.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "GO": "https://nfe.sefaz.go.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "MA": "https://nfe.sefaz.ma.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "MT": "https://nfe.sefaz.mt.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "MS": "https://nfe.sefaz.ms.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "MG": "https://nfe.sefaz.mg.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "PA": "https://nfe.sefaz.pa.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "PB": "https://nfe.sefaz.pb.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "PR": "https://nfe.sefaz.pr.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "PE": "https://nfe.sefaz.pe.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "PI": "https://nfe.sefaz.pi.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RJ": "https://nfe.sefaz.rj.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RN": "https://nfe.sefaz.rn.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RS": "https://nfe.sefaz.rs.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RO": "https://nfe.sefaz.ro.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "RR": "https://nfe.sefaz.rr.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "SC": "https://nfe.sefaz.sc.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "SP": "https://nfe.sefaz.sp.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "SE": "https://nfe.sefaz.se.gov.br/nfeweb/services/NfeStatusServico2.asmx",
    "TO": "https://nfe.sefaz.to.gov.br/nfeweb/services/NfeStatusServico2.asmx",
}

NACIONAL_URL = "https://www.nfe.fazenda.gov.br/NFeStatusServico/NFeStatusServico2.asmx"

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

UF_CODES = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17"
}

async def consultar_status_soap(url: str, uf_code: str):
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

@app.get("/sefaz/status")
async def status_sefaz(uf: str):
    uf = uf.upper()
    if uf not in SEFAZ_UF_URLS:
        raise HTTPException(status_code=400, detail="UF inválida")
    
    status_uf = await consultar_status_soap(SEFAZ_UF_URLS[uf], UF_CODES[uf])
    status_nacional = await consultar_status_soap(NACIONAL_URL, UF_CODES[uf])
    
    return {
        "uf": uf,
        "status_uf": status_uf,
        "status_nacional": status_nacional
    }
