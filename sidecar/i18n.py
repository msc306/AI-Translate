"""Texts of the sidecar in the language of the user interface.

German is the source language: the code keeps the German text and passes it through `tr()`, which
looks it up in CATALOG. A text without a translation is returned in German.

    tr("Unbekannter Befehl: {cmd}", cmd="foo")

Call `tr()` when the text is used, never while a module is imported, so that a later
`set_language()` takes effect everywhere.
"""

DEFAULT = "de"
LANGUAGES = ("de", "en", "es", "fr")

# English names for prompts that ask a model to answer the user in the interface language.
_NAMES = {"de": "German", "en": "English", "es": "Spanish", "fr": "French"}

# One assignment of a string is atomic, so worker threads may read this without a lock.
_current = DEFAULT


def normalize(code) -> str:
    """Return a supported language code; anything else becomes German."""
    code = str(code or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGUAGES else DEFAULT


def set_language(code) -> str:
    """Switch the language of all texts; returns the code that is now active."""
    global _current
    _current = normalize(code)
    return _current


def get_language() -> str:
    return _current


def language_name(code: str | None = None) -> str:
    """English name of the interface language ("German", "English", "Spanish", "French")."""
    return _NAMES[normalize(code) if code else _current]


def tr(text: str, **values) -> str:
    """Return the German source text in the current language, with {placeholders} filled in."""
    language = _current
    if language != DEFAULT:
        text = CATALOG.get(text, {}).get(language) or text
    if not values:
        return text
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


CATALOG = {
    # ---- general ----
    "Ungültige Anfrage": {
        "en": "Invalid request",
        "es": "Solicitud no válida",
        "fr": "Requête non valide",
    },
    "Abgebrochen": {
        "en": "Cancelled",
        "es": "Cancelado",
        "fr": "Annulé",
    },
    "Abgebrochen.": {
        "en": "Cancelled.",
        "es": "Cancelado.",
        "fr": "Annulé.",
    },
    "Fehler": {
        "en": "Error",
        "es": "Error",
        "fr": "Erreur",
    },
    "Unbekannter Befehl: {cmd}": {
        "en": "Unknown command: {cmd}",
        "es": "Comando desconocido: {cmd}",
        "fr": "Commande inconnue : {cmd}",
    },

    # ---- local models and runtime ----
    "Modelldatei fehlt: {path}": {
        "en": "Model file is missing: {path}",
        "es": "Falta el archivo del modelo: {path}",
        "fr": "Fichier de modèle introuvable : {path}",
    },
    "Kein Modell für die Größe '{size}' gefunden. In den Einstellungen lässt sich eine Modelldatei auswählen.": {
        "en": "No model found for the size '{size}'. You can choose a model file in the settings.",
        "es": "No se encontró ningún modelo para el tamaño '{size}'. Puedes elegir un archivo de modelo en los ajustes.",
        "fr": "Aucun modèle trouvé pour la taille '{size}'. Vous pouvez choisir un fichier de modèle dans les paramètres.",
    },
    "Die Grafikkarte ({vendor}) lässt sich nicht abfragen. In den Einstellungen unter „Lokale Modelle“ "
    "lässt sich eine andere Karte oder der Prozessor wählen.": {
        "en": "The graphics card ({vendor}) cannot be queried. Under “Local models” in the settings you can "
              "choose another card or the processor.",
        "es": "No se puede consultar la tarjeta gráfica ({vendor}). En los ajustes, en «Modelos locales», "
              "puede elegir otra tarjeta o el procesador.",
        "fr": "La carte graphique ({vendor}) ne peut pas être interrogée. Dans les paramètres, sous « Modèles "
              "locaux », vous pouvez choisir une autre carte ou le processeur.",
    },
    "Zu wenig freier VRAM: {free} MB frei, benötigt werden {need} MB plus {reserve} MB Reserve.": {
        "en": "Not enough free VRAM: {free} MB free, {need} MB needed plus a reserve of {reserve} MB.",
        "es": "No hay suficiente VRAM libre: {free} MB libres, se necesitan {need} MB más {reserve} MB de reserva.",
        "fr": "VRAM libre insuffisante : {free} Mo libres, {need} Mo nécessaires plus {reserve} Mo de réserve.",
    },
    "llama-server nicht gefunden: {path}": {
        "en": "llama-server not found: {path}",
        "es": "No se encontró llama-server: {path}",
        "fr": "llama-server introuvable : {path}",
    },
    "Keine llama.cpp-Laufzeit gefunden. Sie lässt sich in den Einstellungen herunterladen.": {
        "en": "No llama.cpp runtime found. You can download it in the settings.",
        "es": "No se encontró el entorno de ejecución de llama.cpp. Puedes descargarlo en los ajustes.",
        "fr": "Aucun environnement d'exécution llama.cpp trouvé. Vous pouvez le télécharger dans les paramètres.",
    },
    "Modell konnte nicht geladen werden (Exit {code}).": {
        "en": "The model could not be loaded (exit code {code}).",
        "es": "No se pudo cargar el modelo (código de salida {code}).",
        "fr": "Le modèle n'a pas pu être chargé (code de sortie {code}).",
    },
    "Zeitueberschreitung beim Laden des Modells.": {
        "en": "Loading the model timed out.",
        "es": "Se agotó el tiempo de espera al cargar el modelo.",
        "fr": "Le chargement du modèle a dépassé le délai imparti.",
    },
    "llama-server meldet {status}: {detail}": {
        "en": "llama-server reports {status}: {detail}",
        "es": "llama-server responde {status}: {detail}",
        "fr": "llama-server signale {status} : {detail}",
    },

    # ---- explain and clarify ----
    "Was ist gemeint?": {
        "en": "What is meant?",
        "es": "¿A qué se refiere?",
        "fr": "Que faut-il comprendre ?",
    },
    "Es gibt noch keine Übersetzung zum Erklären.": {
        "en": "There is no translation to explain yet.",
        "es": "Todavía no hay ninguna traducción que explicar.",
        "fr": "Il n'y a pas encore de traduction à expliquer.",
    },
    "Erklären geht nur für Texte bis {limit} Zeichen.": {
        "en": "Explanations are only available for texts of up to {limit} characters.",
        "es": "Solo se pueden explicar textos de hasta {limit} caracteres.",
        "fr": "L'explication n'est possible que pour les textes de {limit} caractères au maximum.",
    },
    "Das Modell hat keine verwertbare Erklärung geliefert.": {
        "en": "The model did not return a usable explanation.",
        "es": "El modelo no ha devuelto una explicación utilizable.",
        "fr": "Le modèle n'a pas fourni d'explication exploitable.",
    },

    # ---- output checks ----
    "Die Übersetzung ist leer.": {
        "en": "The translation is empty.",
        "es": "La traducción está vacía.",
        "fr": "La traduction est vide.",
    },
    "Der Text wurde offenbar nicht übersetzt.": {
        "en": "The text does not seem to have been translated.",
        "es": "Parece que el texto no se ha traducido.",
        "fr": "Le texte ne semble pas avoir été traduit.",
    },
    "Die Ausgabe scheint nicht in der Zielsprache zu sein.": {
        "en": "The output does not seem to be in the target language.",
        "es": "El resultado no parece estar en el idioma de destino.",
        "fr": "Le résultat ne semble pas être dans la langue cible.",
    },
    "Die Übersetzung ist auffällig kurz – möglicherweise fehlt ein Teil.": {
        "en": "The translation is unusually short – part of the text may be missing.",
        "es": "La traducción es llamativamente corta: puede que falte una parte.",
        "fr": "La traduction est étonnamment courte : il manque peut-être une partie.",
    },
    "Die Übersetzung ist auffällig lang – möglicherweise wurde etwas hinzugefügt.": {
        "en": "The translation is unusually long – something may have been added.",
        "es": "La traducción es llamativamente larga: puede que se haya añadido algo.",
        "fr": "La traduction est étonnamment longue : quelque chose a peut-être été ajouté.",
    },

    # ---- styles ----
    "Neutral": {
        "en": "Neutral",
        "es": "Neutro",
        "fr": "Neutre",
    },
    "Förmlich": {
        "en": "Formal",
        "es": "Formal",
        "fr": "Soutenu",
    },
    "Locker": {
        "en": "Casual",
        "es": "Informal",
        "fr": "Décontracté",
    },
    "Wörtlich": {
        "en": "Literal",
        "es": "Literal",
        "fr": "Littéral",
    },

    # ---- engines ----
    "Lokal (GPU)": {
        "en": "Local (GPU)",
        "es": "Local (GPU)",
        "fr": "Local (GPU)",
    },
    "Claude (API-Schlüssel)": {
        "en": "Claude (API key)",
        "es": "Claude (clave de API)",
        "fr": "Claude (clé API)",
    },
    "Claude (Abo: Pro/Max)": {
        "en": "Claude (subscription: Pro/Max)",
        "es": "Claude (suscripción: Pro/Max)",
        "fr": "Claude (abonnement : Pro/Max)",
    },
    "OpenAI-kompatibel (API-Schlüssel)": {
        "en": "OpenAI-compatible (API key)",
        "es": "Compatible con OpenAI (clave de API)",
        "fr": "Compatible OpenAI (clé API)",
    },
    "ChatGPT (Abo, über Codex)": {
        "en": "ChatGPT (subscription, via Codex)",
        "es": "ChatGPT (suscripción, mediante Codex)",
        "fr": "ChatGPT (abonnement, via Codex)",
    },
    "API-Schlüssel fehlt": {
        "en": "API key missing",
        "es": "Falta la clave de API",
        "fr": "Clé API manquante",
    },
    "Modell fehlt": {
        "en": "Model missing",
        "es": "Falta el modelo",
        "fr": "Modèle manquant",
    },
    "Claude Code nicht installiert": {
        "en": "Claude Code not installed",
        "es": "Claude Code no está instalado",
        "fr": "Claude Code n'est pas installé",
    },
    "OpenRouter (API-Schlüssel, viele Modelle)": {
        "en": "OpenRouter (API key, many models)",
        "es": "OpenRouter (clave de API, muchos modelos)",
        "fr": "OpenRouter (clé API, nombreux modèles)",
    },
    "Kein OpenRouter-API-Schlüssel hinterlegt (Einstellungen → Anbieter).": {
        "en": "No OpenRouter API key stored (Settings → Providers).",
        "es": "No hay clave de API de OpenRouter guardada (Ajustes → Proveedores).",
        "fr": "Aucune clé API OpenRouter enregistrée (Paramètres → Fournisseurs).",
    },
    "Für OpenRouter ist kein Modell eingestellt.": {
        "en": "No model is set for OpenRouter.",
        "es": "No hay ningún modelo configurado para OpenRouter.",
        "fr": "Aucun modèle n'est défini pour OpenRouter.",
    },
    "Codex-CLI nicht installiert": {
        "en": "Codex CLI not installed",
        "es": "La CLI de Codex no está instalada",
        "fr": "La CLI Codex n'est pas installée",
    },
    "Unbekannter Anbieter: {engine}": {
        "en": "Unknown provider: {engine}",
        "es": "Proveedor desconocido: {engine}",
        "fr": "Fournisseur inconnu : {engine}",
    },
    "{label} ist in den Einstellungen nicht aktiviert.": {
        "en": "{label} is not enabled in the settings.",
        "es": "{label} no está activado en los ajustes.",
        "fr": "{label} n'est pas activé dans les paramètres.",
    },

    # ---- cloud providers ----
    "Ungültige Adresse: {url}": {
        "en": "Invalid address: {url}",
        "es": "Dirección no válida: {url}",
        "fr": "Adresse non valide : {url}",
    },
    "{name} meldet HTTP {status}: {detail}": {
        "en": "{name} reports HTTP {status}: {detail}",
        "es": "{name} responde HTTP {status}: {detail}",
        "fr": "{name} signale HTTP {status} : {detail}",
    },
    "{name} nicht erreichbar: {error}": {
        "en": "{name} cannot be reached: {error}",
        "es": "No se puede conectar con {name}: {error}",
        "fr": "{name} est injoignable : {error}",
    },
    "Kein Claude-API-Schlüssel hinterlegt (Einstellungen → Anbieter).": {
        "en": "No Claude API key has been entered (Settings → Providers).",
        "es": "No se ha introducido ninguna clave de API de Claude (Ajustes → Proveedores).",
        "fr": "Aucune clé API Claude n'est enregistrée (Paramètres → Fournisseurs).",
    },
    "Kein OpenAI-API-Schlüssel hinterlegt (Einstellungen → Anbieter).": {
        "en": "No OpenAI API key has been entered (Settings → Providers).",
        "es": "No se ha introducido ninguna clave de API de OpenAI (Ajustes → Proveedores).",
        "fr": "Aucune clé API OpenAI n'est enregistrée (Paramètres → Fournisseurs).",
    },
    "Claude hat die Übersetzung dieses Textes abgelehnt.": {
        "en": "Claude declined to translate this text.",
        "es": "Claude se ha negado a traducir este texto.",
        "fr": "Claude a refusé de traduire ce texte.",
    },
    "Claude-API: {detail}": {
        "en": "Claude API: {detail}",
        "es": "API de Claude: {detail}",
        "fr": "API Claude : {detail}",
    },
    "Für den OpenAI-kompatiblen Anbieter ist kein Modell eingestellt.": {
        "en": "No model is set for the OpenAI-compatible provider.",
        "es": "No hay ningún modelo configurado para el proveedor compatible con OpenAI.",
        "fr": "Aucun modèle n'est défini pour le fournisseur compatible OpenAI.",
    },
    "Der Anbieter meldet: {detail}": {
        "en": "The provider reports: {detail}",
        "es": "El proveedor responde: {detail}",
        "fr": "Le fournisseur signale : {detail}",
    },
    "Modellliste nicht abrufbar: {error}": {
        "en": "The model list could not be retrieved: {error}",
        "es": "No se pudo obtener la lista de modelos: {error}",
        "fr": "Impossible de récupérer la liste des modèles : {error}",
    },
    "{name} lässt sich nicht starten: {error}": {
        "en": "{name} could not be started: {error}",
        "es": "No se pudo iniciar {name}: {error}",
        "fr": "Impossible de démarrer {name} : {error}",
    },
    "Claude Code wurde nicht gefunden. Installieren und einmal `claude` starten, um sich mit dem Abo anzumelden.": {
        "en": "Claude Code was not found. Install it and run `claude` once to sign in with your subscription.",
        "es": "No se encontró Claude Code. Instálalo y ejecuta `claude` una vez para iniciar sesión con tu suscripción.",
        "fr": "Claude Code est introuvable. Installez-le et lancez `claude` une fois pour vous connecter avec votre abonnement.",
    },
    "Claude Code hat nicht geantwortet.": {
        "en": "Claude Code did not respond.",
        "es": "Claude Code no ha respondido.",
        "fr": "Claude Code n'a pas répondu.",
    },
    "Die Codex-CLI wurde nicht gefunden. Installieren (npm i -g @openai/codex) und einmal `codex login` ausführen.": {
        "en": "The Codex CLI was not found. Install it (npm i -g @openai/codex) and run `codex login` once.",
        "es": "No se encontró la CLI de Codex. Instálala (npm i -g @openai/codex) y ejecuta `codex login` una vez.",
        "fr": "La CLI Codex est introuvable. Installez-la (npm i -g @openai/codex) et exécutez `codex login` une fois.",
    },
    "Codex hat nicht geantwortet.": {
        "en": "Codex did not respond.",
        "es": "Codex no ha respondido.",
        "fr": "Codex n'a pas répondu.",
    },
    "{message} – bitte einmal `{command}` im Terminal ausführen und anmelden.": {
        "en": "{message} – please run `{command}` once in a terminal and sign in.",
        "es": "{message} – ejecuta `{command}` una vez en la terminal e inicia sesión.",
        "fr": "{message} – veuillez exécuter `{command}` une fois dans un terminal et vous connecter.",
    },

    # ---- downloads ----
    "llama.cpp-Laufzeit für NVIDIA-Grafikkarten ({tag})": {
        "en": "llama.cpp runtime for NVIDIA graphics cards ({tag})",
        "es": "Entorno de ejecución de llama.cpp para tarjetas gráficas NVIDIA ({tag})",
        "fr": "Environnement d'exécution llama.cpp pour cartes graphiques NVIDIA ({tag})",
    },
    "llama.cpp-Laufzeit für Mac mit Apple Silicon, Metal ({tag})": {
        "en": "llama.cpp runtime for Macs with Apple silicon, Metal ({tag})",
        "es": "Entorno de ejecución de llama.cpp para Mac con Apple silicon, Metal ({tag})",
        "fr": "Environnement d'exécution llama.cpp pour Mac avec puce Apple, Metal ({tag})",
    },
    "llama.cpp-Laufzeit für Mac mit Intel-Prozessor ({tag})": {
        "en": "llama.cpp runtime for Macs with an Intel processor ({tag})",
        "es": "Entorno de ejecución de llama.cpp para Mac con procesador Intel ({tag})",
        "fr": "Environnement d'exécution llama.cpp pour Mac avec processeur Intel ({tag})",
    },
    "llama.cpp-Laufzeit für AMD- und Intel-Grafikkarten, Vulkan ({tag})": {
        "en": "llama.cpp runtime for AMD and Intel graphics cards, Vulkan ({tag})",
        "es": "Entorno de ejecución de llama.cpp para tarjetas gráficas AMD e Intel, Vulkan ({tag})",
        "fr": "Environnement d'exécution llama.cpp pour cartes graphiques AMD et Intel, Vulkan ({tag})",
    },
    "llama.cpp-Laufzeit nur für den Prozessor ({tag})": {
        "en": "llama.cpp runtime for the processor only ({tag})",
        "es": "Entorno de ejecución de llama.cpp solo para el procesador ({tag})",
        "fr": "Environnement d'exécution llama.cpp pour le processeur uniquement ({tag})",
    },
    "Gemma 4 E2B (kleines Modell, Apache-2.0)": {
        "en": "Gemma 4 E2B (small model, Apache-2.0)",
        "es": "Gemma 4 E2B (modelo pequeño, Apache-2.0)",
        "fr": "Gemma 4 E2B (petit modèle, Apache-2.0)",
    },
    "Bereits vorhanden.": {
        "en": "Already installed.",
        "es": "Ya está instalado.",
        "fr": "Déjà installé.",
    },
    "Abgebrochen. Der bereits geladene Teil bleibt für die Fortsetzung erhalten.": {
        "en": "Cancelled. The part already downloaded is kept so the download can be resumed.",
        "es": "Cancelado. La parte ya descargada se conserva para poder reanudar la descarga.",
        "fr": "Annulé. La partie déjà téléchargée est conservée pour pouvoir reprendre le téléchargement.",
    },
    "Download fehlgeschlagen: {error}": {
        "en": "Download failed: {error}",
        "es": "La descarga ha fallado: {error}",
        "fr": "Le téléchargement a échoué : {error}",
    },
    "Download von {name} fehlgeschlagen: {error}": {
        "en": "Download of {name} failed: {error}",
        "es": "La descarga de {name} ha fallado: {error}",
        "fr": "Le téléchargement de {name} a échoué : {error}",
    },
    "Unbekannter Download: {item}": {
        "en": "Unknown download: {item}",
        "es": "Descarga desconocida: {item}",
        "fr": "Téléchargement inconnu : {item}",
    },
    "Die Prüfsumme von {name} stimmt nicht. Die Datei wurde verworfen.": {
        "en": "The checksum of {name} does not match. The file was discarded.",
        "es": "La suma de comprobación de {name} no coincide. El archivo se ha descartado.",
        "fr": "La somme de contrôle de {name} ne correspond pas. Le fichier a été supprimé.",
    },
    "Zu wenig Speicherplatz: {need} MB nötig, {free} MB frei ({drive}).": {
        "en": "Not enough disk space: {need} MB needed, {free} MB free ({drive}).",
        "es": "No hay suficiente espacio en disco: se necesitan {need} MB, hay {free} MB libres ({drive}).",
        "fr": "Espace disque insuffisant : {need} Mo nécessaires, {free} Mo libres ({drive}).",
    },
    "Downloads laufen nur über https://.": {
        "en": "Downloads are only made over https://.",
        "es": "Las descargas solo se realizan mediante https://.",
        "fr": "Les téléchargements se font uniquement via https://.",
    },
    "Der Server sendet keine Daten mehr.": {
        "en": "The server has stopped sending data.",
        "es": "El servidor ha dejado de enviar datos.",
        "fr": "Le serveur n'envoie plus de données.",
    },
    "Der Server leitet auf eine unsichere Adresse um.": {
        "en": "The server redirects to an insecure address.",
        "es": "El servidor redirige a una dirección no segura.",
        "fr": "Le serveur redirige vers une adresse non sécurisée.",
    },
    "Verbindung vorzeitig beendet": {
        "en": "Connection closed prematurely",
        "es": "La conexión se cerró antes de tiempo",
        "fr": "Connexion interrompue prématurément",
    },
    "Im Archiv fehlt {name}.": {
        "en": "{name} is missing from the archive.",
        "es": "Falta {name} en el archivo comprimido.",
        "fr": "{name} est absent de l'archive.",
    },
    "whisper.cpp-Spracherkennung ({tag})": {
        "en": "whisper.cpp speech recognition ({tag})",
        "es": "Reconocimiento de voz whisper.cpp ({tag})",
        "fr": "Reconnaissance vocale whisper.cpp ({tag})",
    },
    "Whisper small (Sprachmodell, MIT)": {
        "en": "Whisper small (speech model, MIT)",
        "es": "Whisper small (modelo de voz, MIT)",
        "fr": "Whisper small (modèle vocal, MIT)",
    },

    # ---- speech input (speech.py) ----
    "Spracheingabe gibt es nur unter Windows und macOS.": {
        "en": "Speech input is only available on Windows and macOS.",
        "es": "La entrada de voz solo está disponible en Windows y macOS.",
        "fr": "La saisie vocale n'est disponible que sous Windows et macOS.",
    },
    "Für die Aufnahme fehlt ein Aufnahmeprogramm. Bitte ffmpeg oder SoX installieren "
    "(zum Beispiel mit Homebrew: brew install ffmpeg).": {
        "en": "No recording program is installed. Please install ffmpeg or SoX "
              "(for example with Homebrew: brew install ffmpeg).",
        "es": "Falta un programa de grabación. Instale ffmpeg o SoX "
              "(por ejemplo con Homebrew: brew install ffmpeg).",
        "fr": "Aucun programme d'enregistrement n'est installé. Installez ffmpeg ou SoX "
              "(par exemple avec Homebrew : brew install ffmpeg).",
    },
    "Für die Spracheingabe fehlt whisper.cpp. Bitte mit Homebrew installieren "
    "(brew install whisper-cpp) und in den Einstellungen unter „Spracheingabe“ "
    "ein Sprachmodell herunterladen.": {
        "en": "Speech input needs whisper.cpp. Please install it with Homebrew "
              "(brew install whisper-cpp) and download a speech model in the settings under "
              "“Speech input”.",
        "es": "La entrada de voz necesita whisper.cpp. Instálelo con Homebrew "
              "(brew install whisper-cpp) y descargue un modelo de voz en los ajustes, en "
              "«Entrada de voz».",
        "fr": "La saisie vocale nécessite whisper.cpp. Installez-le avec Homebrew "
              "(brew install whisper-cpp) et téléchargez un modèle vocal dans les paramètres, sous "
              "« Saisie vocale ».",
    },
    "Es läuft bereits eine Aufnahme.": {
        "en": "A recording is already running.",
        "es": "Ya hay una grabación en curso.",
        "fr": "Un enregistrement est déjà en cours.",
    },
    "Es läuft keine Aufnahme.": {
        "en": "No recording is running.",
        "es": "No hay ninguna grabación en curso.",
        "fr": "Aucun enregistrement en cours.",
    },
    "Das Mikrofon lässt sich nicht öffnen: {detail}": {
        "en": "The microphone cannot be opened: {detail}",
        "es": "No se puede abrir el micrófono: {detail}",
        "fr": "Impossible d'ouvrir le microphone : {detail}",
    },
    "Es war nichts zu hören. Ist das richtige Mikrofon eingestellt und nicht stummgeschaltet?": {
        "en": "Nothing could be heard. Is the right microphone selected and not muted?",
        "es": "No se oyó nada. ¿Está seleccionado el micrófono correcto y no está silenciado?",
        "fr": "Rien n'a été entendu. Le bon microphone est-il sélectionné et non coupé ?",
    },
    "In der Aufnahme wurde kein Text erkannt.": {
        "en": "No text was recognised in the recording.",
        "es": "No se reconoció ningún texto en la grabación.",
        "fr": "Aucun texte n'a été reconnu dans l'enregistrement.",
    },
    "Für die Spracheingabe fehlt die Spracherkennung. In den Einstellungen unter „Spracheingabe“ lassen sich whisper.cpp und ein Sprachmodell herunterladen.": {
        "en": "Speech recognition is missing. Under “Speech input” in the settings you can download whisper.cpp and a speech model.",
        "es": "Falta el reconocimiento de voz. En los ajustes, en «Entrada de voz», puede descargar whisper.cpp y un modelo de voz.",
        "fr": "La reconnaissance vocale est absente. Dans les paramètres, sous « Saisie vocale », vous pouvez télécharger whisper.cpp et un modèle vocal.",
    },
    "Das gewählte Sprachmodell fehlt: {path}": {
        "en": "The selected speech model is missing: {path}",
        "es": "Falta el modelo de voz elegido: {path}",
        "fr": "Le modèle vocal choisi est introuvable : {path}",
    },
    "Die Spracherkennung ist fehlgeschlagen: {detail}": {
        "en": "Speech recognition failed: {detail}",
        "es": "El reconocimiento de voz ha fallado: {detail}",
        "fr": "La reconnaissance vocale a échoué : {detail}",
    },

    # ---- language packs and phrases ----
    "Sprachpakete werden nur über https:// geladen.": {
        "en": "Language packs are only downloaded over https://.",
        "es": "Los paquetes de idioma solo se descargan mediante https://.",
        "fr": "Les packs de langue ne sont téléchargés que via https://.",
    },
    "Das Sprachpaket ist zu groß.": {
        "en": "The language pack is too large.",
        "es": "El paquete de idioma es demasiado grande.",
        "fr": "Le pack de langue est trop volumineux.",
    },
    "Die gewählte Datei wurde nicht gefunden.": {
        "en": "The selected file was not found.",
        "es": "No se encontró el archivo seleccionado.",
        "fr": "Le fichier sélectionné est introuvable.",
    },
    "Nur selbst installierte Sprachpakete lassen sich entfernen.": {
        "en": "Only language packs you installed yourself can be removed.",
        "es": "Solo se pueden eliminar los paquetes de idioma que hayas instalado tú.",
        "fr": "Seuls les packs de langue que vous avez installés vous-même peuvent être supprimés.",
    },
    "Paketliste nicht abrufbar: {error}": {
        "en": "The pack list could not be retrieved: {error}",
        "es": "No se pudo obtener la lista de paquetes: {error}",
        "fr": "Impossible de récupérer la liste des packs : {error}",
    },
    "Kein Sprachpaket: erwartet wird eine .zip-Datei oder ein Ordner mit manifest.json.": {
        "en": "Not a language pack: a .zip file or a folder containing manifest.json is expected.",
        "es": "No es un paquete de idioma: se espera un archivo .zip o una carpeta con manifest.json.",
        "fr": "Ce n'est pas un pack de langue : un fichier .zip ou un dossier contenant manifest.json est attendu.",
    },
    "Im Sprachpaket fehlt die Datei manifest.json.": {
        "en": "The language pack does not contain a manifest.json file.",
        "es": "Falta el archivo manifest.json en el paquete de idioma.",
        "fr": "Le fichier manifest.json est absent du pack de langue.",
    },
    "Das Sprachpaket ist beschädigt (manifest.json oder phrases.json ungültig).": {
        "en": "The language pack is damaged (manifest.json or phrases.json is invalid).",
        "es": "El paquete de idioma está dañado (manifest.json o phrases.json no es válido).",
        "fr": "Le pack de langue est endommagé (manifest.json ou phrases.json non valide).",
    },
    "Das Sprachpaket hat keine gültige Kennung oder weniger als zwei Sprachen.": {
        "en": "The language pack has no valid ID or fewer than two languages.",
        "es": "El paquete de idioma no tiene un identificador válido o tiene menos de dos idiomas.",
        "fr": "Le pack de langue n'a pas d'identifiant valide ou contient moins de deux langues.",
    },
    "Ausgangs- und Zieltext dürfen nicht leer sein.": {
        "en": "The source and target text must not be empty.",
        "es": "El texto de origen y el de destino no pueden estar vacíos.",
        "fr": "Le texte source et le texte cible ne doivent pas être vides.",
    },
    "Es gibt noch keine eigenen Einträge.": {
        "en": "You have no entries of your own yet.",
        "es": "Todavía no tienes entradas propias.",
        "fr": "Vous n'avez pas encore d'entrées personnelles.",
    },
    "Eigene Phrasen": {
        "en": "My phrases",
        "es": "Mis frases",
        "fr": "Mes expressions",
    },

    # ---- history and export ----
    "Kein gültiger Speicherort.": {
        "en": "Not a valid location to save to.",
        "es": "La ubicación para guardar no es válida.",
        "fr": "L'emplacement d'enregistrement n'est pas valide.",
    },
    "Unbekanntes Format: {fmt}": {
        "en": "Unknown format: {fmt}",
        "es": "Formato desconocido: {fmt}",
        "fr": "Format inconnu : {fmt}",
    },
    "AI Translate: Verlauf": {
        "en": "AI Translate: History",
        "es": "AI Translate: Historial",
        "fr": "AI Translate : Historique",
    },
    "Zeit": {
        "en": "Time",
        "es": "Hora",
        "fr": "Heure",
    },
    "Richtung": {
        "en": "Direction",
        "es": "Dirección",
        "fr": "Sens",
    },
    "Anbieter": {
        "en": "Provider",
        "es": "Proveedor",
        "fr": "Fournisseur",
    },
    "Ausgangstext": {
        "en": "Source text",
        "es": "Texto de origen",
        "fr": "Texte source",
    },
    "Übersetzung": {
        "en": "Translation",
        "es": "Traducción",
        "fr": "Traduction",
    },
    "Korrektur": {
        "en": "Correction",
        "es": "Corrección",
        "fr": "Correction",
    },

    # ---- text recognition ----
    "Die Texterkennung aus Bildern gibt es nur unter Windows und macOS.": {
        "en": "Text recognition from images is only available on Windows and macOS.",
        "es": "El reconocimiento de texto en imágenes solo está disponible en Windows y macOS.",
        "fr": "La reconnaissance de texte dans les images n'est disponible que sous Windows et macOS.",
    },
    "In der Zwischenablage liegt weder Text noch ein Bild.": {
        "en": "The clipboard contains neither text nor an image.",
        "es": "El portapapeles no contiene ni texto ni una imagen.",
        "fr": "Le presse-papiers ne contient ni texte ni image.",
    },
    "Die Bilddatei wurde nicht gefunden.": {
        "en": "The image file was not found.",
        "es": "No se encontró el archivo de imagen.",
        "fr": "Le fichier image est introuvable.",
    },
    "In Windows ist keine Sprache für die Texterkennung installiert (Einstellungen → Zeit und Sprache → "
    "Sprache → Optionale Sprachfeatures).": {
        "en": "No language for text recognition is installed in Windows (Settings → Time & language → "
              "Language → Optional language features).",
        "es": "En Windows no hay ningún idioma instalado para el reconocimiento de texto (Configuración → "
              "Hora e idioma → Idioma → Características de idioma opcionales).",
        "fr": "Aucune langue n'est installée dans Windows pour la reconnaissance de texte (Paramètres → "
              "Heure et langue → Langue → Fonctionnalités linguistiques facultatives).",
    },
    "Im Bild wurde kein Text erkannt.": {
        "en": "No text was recognised in the image.",
        "es": "No se ha reconocido ningún texto en la imagen.",
        "fr": "Aucun texte n'a été reconnu dans l'image.",
    },
    "Die Texterkennung ist fehlgeschlagen.": {
        "en": "Text recognition failed.",
        "es": "El reconocimiento de texto ha fallado.",
        "fr": "La reconnaissance de texte a échoué.",
    },
}

# ---- language names (languages.CATALOG labels): German -> (en, es, fr) ----
_LANGUAGE_LABELS = {
    "Deutsch": ("German", "Alemán", "Allemand"),
    "Englisch": ("English", "Inglés", "Anglais"),
    "Französisch": ("French", "Francés", "Français"),
    "Spanisch": ("Spanish", "Español", "Espagnol"),
    "Italienisch": ("Italian", "Italiano", "Italien"),
    "Portugiesisch": ("Portuguese", "Portugués", "Portugais"),
    "Niederländisch": ("Dutch", "Neerlandés", "Néerlandais"),
    "Polnisch": ("Polish", "Polaco", "Polonais"),
    "Tschechisch": ("Czech", "Checo", "Tchèque"),
    "Schwedisch": ("Swedish", "Sueco", "Suédois"),
    "Dänisch": ("Danish", "Danés", "Danois"),
    "Norwegisch": ("Norwegian", "Noruego", "Norvégien"),
    "Finnisch": ("Finnish", "Finés", "Finnois"),
    "Türkisch": ("Turkish", "Turco", "Turc"),
    "Rumänisch": ("Romanian", "Rumano", "Roumain"),
    "Ungarisch": ("Hungarian", "Húngaro", "Hongrois"),
    "Litauisch": ("Lithuanian", "Lituano", "Lituanien"),
    "Lettisch": ("Latvian", "Letón", "Letton"),
    "Griechisch": ("Greek", "Griego", "Grec"),
    "Russisch": ("Russian", "Ruso", "Russe"),
    "Ukrainisch": ("Ukrainian", "Ucraniano", "Ukrainien"),
    "Arabisch": ("Arabic", "Árabe", "Arabe"),
    "Hebräisch": ("Hebrew", "Hebreo", "Hébreu"),
    "Chinesisch": ("Chinese", "Chino", "Chinois"),
    "Japanisch": ("Japanese", "Japonés", "Japonais"),
    "Koreanisch": ("Korean", "Coreano", "Coréen"),
}
CATALOG.update({german: dict(zip(("en", "es", "fr"), names)) for german, names in _LANGUAGE_LABELS.items()})
