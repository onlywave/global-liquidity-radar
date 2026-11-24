# Global Liquidity & Stress Radar (GLSI)

Cruscotto live della liquidità globale e dello stress finanziario.

Sito: https://onlywave.github.io/global-liquidity-radar/

## Cosa mostra

- **Indicatore GLSI 0–100**: `Score = 100 × Φ(½·Liquidità − ½·Stress)`, con cinque regimi (Siccità < 20, Stretta 20–40, Neutrale 40–60, Allentamento 60–80, Abbondanza > 80).
- **Liquidità**: liquidità netta globale (attivo Fed − TGA − reverse repo + attivo BCE + attivo BoJ, in dollari), M2 USA, dollaro ampio.
- **Stress**: Chicago Fed NFCI, St. Louis Fed FSI, VIX, spread high yield.
- **Storico** dello score dal 2003, **episodi di stress degli ultimi 20 anni** con livelli di picco, drawdown e rendimenti successivi dell'S&P 500, e gli **interventi** di banche centrali e governi.
- **Alert**: cambio di regime, vicinanza a una soglia, ±10 punti in 4 settimane, VIX sopra 30, NFCI sopra zero, inizio di un episodio di stress, liquidità netta −2% in 4 settimane.

## Aggiornamento

GitHub Actions esegue `scripts/build.py` ogni 3 ore (e a ogni modifica di script o config): scarica le serie da FRED, ricalcola tutto e scrive `data/*.json`. I dati ufficiali escono con il loro calendario (bilancio Fed il giovedì, NFCI il mercoledì, VIX ogni giorno): la pagina mostra la data dell'ultimo dato di ogni serie.

## Notifiche

- **GitHub**: ogni nuovo alert apre una issue con etichetta `alert`; GitHub la notifica via e-mail al proprietario del repository.
- **Telegram** (opzionale): secret `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
- **E-mail diretta** (opzionale, Gmail): secret `SMTP_USER`, `SMTP_PASS` (password per le app) e `ALERT_EMAIL_TO`.
- **Browser**: pulsante "Attiva notifiche" sulla pagina (funziona con la pagina aperta).

## Catalogo eventi

`config/events.json` contiene i nomi degli episodi e gli interventi. Livelli e date di picco vengono sempre dai dati; per aggiungere un intervento basta una riga nel file.

Ricostruzione indipendente ispirata al gauge GLSI di James Easton: i valori non coincidono con l'originale. Strumento di analisi, non consulenza finanziaria.
