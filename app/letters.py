"""Writes the letter that asks a company to close the account of someone who has died.

The model writes the human part: a short, calm request in the family's language. It is not allowed to
write facts. Its text is rejected if it contains a digit, an amount, a date, an email address or a link,
and a fixed template is used instead. Every fact (whose account, when they died, which charges were taken
since) is added underneath by code, from the statement itself."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from . import names

LANGUAGES = {"en": "English", "it": "Italian", "de": "German", "es": "Spanish", "fr": "French"}

PROMPT = """Write the body of a short letter to {merchant}, in {language}, from {sender} ({relation} of
{holder}). {holder} has died. Ask them to close the account or subscription, to stop all future charges,
and to refund any charges taken after the date of death. The tone is calm, polite and brief: no
condolences to yourself, no drama, five sentences at most.
Do not write any number, date, amount, account number, email address or link: they are added below the
letter automatically. Do not write a greeting line or a signature. Reply with the body only."""

TEMPLATES = {
    "en": ("I am writing on behalf of the family of {holder}, who has died. Please close the account or "
           "subscription in their name, stop all future charges, and refund any payments taken after the date "
           "of death. The details are below. Thank you for your help."),
    "it": ("Vi scrivo per conto della famiglia di {holder}, che ci ha lasciato. Vi chiedo di chiudere "
           "l'account o l'abbonamento a suo nome, di interrompere ogni addebito futuro e di rimborsare i "
           "pagamenti addebitati dopo la data del decesso. Trovate i dettagli qui sotto. Grazie per l'aiuto."),
    "de": ("Ich schreibe im Namen der Familie von {holder}. {holder} ist verstorben. Bitte schließen Sie das Konto "
           "oder Abonnement auf diesen Namen, stoppen Sie alle weiteren Abbuchungen und erstatten Sie die "
           "Zahlungen nach dem Todestag. Die Angaben finden Sie unten. Vielen Dank."),
    "es": ("Les escribo en nombre de la familia de {holder}, que ha fallecido. Les ruego que cierren la cuenta "
           "o suscripción a su nombre, detengan todos los cargos futuros y reembolsen los pagos cobrados "
           "después de la fecha del fallecimiento. Los detalles están abajo. Gracias por su ayuda."),
    "fr": ("Je vous écris au nom de la famille de {holder}, suite à son décès. Merci de clôturer le compte ou "
           "l'abonnement à son nom, d'arrêter tout prélèvement futur et de rembourser les paiements prélevés "
           "après la date du décès. Les détails figurent ci-dessous. Merci de votre aide."),
}
LABELS = {
    "en": ("Account holder", "Date of death", "Charges since that date", "Total", "Dear {merchant} team,", "Kind regards,"),
    "it": ("Intestatario", "Data del decesso", "Addebiti da quella data", "Totale", "Gentile servizio clienti di {merchant},", "Cordiali saluti,"),
    "de": ("Kontoinhaber", "Todestag", "Abbuchungen seit diesem Tag", "Summe", "Sehr geehrtes {merchant}-Team,", "Mit freundlichen Grüßen,"),
    "es": ("Titular", "Fecha de fallecimiento", "Cargos desde esa fecha", "Total", "Estimado equipo de {merchant}:", "Atentamente,"),
    "fr": ("Titulaire", "Date du décès", "Prélèvements depuis cette date", "Total", "Madame, Monsieur, ({merchant})", "Cordialement,"),
}

_FORBIDDEN = re.compile(r"\d|[$€£¥]|https?://|www\.|@|\[|\]|\{|\}")


def acceptable(text: str) -> bool:
    text = text.strip()
    return 40 <= len(text) <= 1200 and not _FORBIDDEN.search(text)


def write(merchant: str, holder: str, died: date, charges: list[tuple[date, Decimal]], sender: str, relation: str,
          language: str = "en", currency: str = "EUR") -> dict:
    language = language if language in LANGUAGES else "en"
    body, source = "", "template"
    if names.enabled():
        try:
            text = names._chat(PROMPT.format(merchant=merchant, language=LANGUAGES[language], sender=sender or "a relative",
                                             relation=relation or "a relative", holder=holder))
            text = re.sub(r"^```\w*|```$", "", text.strip()).strip()
            if acceptable(text):
                body, source = text, names.model_label()
        except Exception:  # the template is always there
            pass
    if not body:
        body = TEMPLATES[language].format(holder=holder)
    lab = LABELS[language]
    since = [(d, a) for d, a in charges if d > died]
    total = sum((a for _, a in since), Decimal("0"))
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency, currency + " ")
    facts = [f"{lab[0]}: {holder}", f"{lab[1]}: {died.isoformat()}"]
    if since:
        facts.append(f"{lab[2]}:")
        facts += [f"  {d.isoformat()}  {sym}{a:.2f}" for d, a in since]
        facts.append(f"{lab[3]}: {sym}{total:.2f}")
    text = "\n\n".join([lab[4].format(merchant=merchant), body, "\n".join(facts), lab[5] + "\n" + (sender or "")]).strip()
    return {"text": text, "written_by": source, "charges_since": len(since), "total_since": f"{total:.2f}"}
