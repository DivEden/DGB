# 🛠️ DGB Værktøjer

En samling af webbaserede værktøjer til Den Gamle By's museumsfaglige afdeling.

## 🚀 Funktioner

### 📋 Sammenfletter
Flet objektnumre med data fra arkivet på tre forskellige måder:

- **📊 Excel Sammenfletning**: Sammenflet to Excel filer med robust matching
- **🔌 API Integration**: Upload Excel med objektnumre og vælg specifikke felter (klar til fremtidig API)
- **✍️ Manuel Indtastning**: Indtast objektnumre direkte uden Excel upload

### 🖼️ Billedbehandling
Professionel billedbehandling i tre modes:

- **⚡ Simpel Resize**: Ubegrænset antal billeder, KB-baseret komprimering, behold filnavne
- **📂 Gruppering**: Organiser billeder i grupper med automatisk omdøbning
- **📄 Individuelle**: Behandl billeder individuelt med tilpassede navne

### 🗂️ Tekstnormalisering
Normaliser og strukturer arkivnumre og tekst data.

## 🏗️ Teknisk Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Billedbehandling**: Pillow (PIL)
- **Data**: Pandas for Excel håndtering
- **Database**: SQLite til feedback system
- **Deployment**: Render.com / Railway

## 📦 Installation

### Lokal Development

```bash
# Clone repository
git clone https://github.com/DivEden/DGB.git
cd DGB

# Installer dependencies
pip install -r requirements.txt

# Kør applikationen
python main.py
```

Applikationen kører på `http://localhost:5000`

### Deployment

Applikationen er konfigureret til deployment på Render.com eller Railway med:
- `render.yaml` til Render.com
- `Procfile` til Railway/Heroku

## 🔧 Konfiguration

### Environment Variables
```bash
# For development mode (bruges test mapper i stedet for netværksdrev)
DGB_DEV_MODE=true

# For production på cloud services
RENDER=true
# eller
RAILWAY_ENVIRONMENT=true
```

### Museum Mappestruktur
Applikationen kan automatisk organisere filer til museumsmapper:
```
\\dgb-file01\Museum\Museumsfaglig afdeling\0 Museets Samlinger\6 Genstandsfotos\
├── Sag 0001-0099/
│   ├── Sag 0010-0019/
│   │   ├── 0017/
│   │   │   └── museumsklar/
└── ...
```

## 📱 Funktionalitet

### Sammenfletter Features
- **Robust matching**: Ignorerer mellemrum, tegnsætning og store/små bogstaver
- **Basis-nøgle fallback**: Matcher på prefix + første tal-blok
- **Forhåndsvisning**: Se data før sammenfletning
- **Excel download**: Få resultater som Excel fil
- **API-klar**: Struktureret til fremtidig API integration

### Resizer Features
- **Ubegrænset upload**: Ingen begrænsning på antal eller størrelse (Simple Resize)
- **KB-præcis komprimering**: Rammer næsten eksakt mål-størrelse
- **Intelligent algoritme**: Justerer både kvalitet og dimension
- **Museum integration**: Automatisk organisering til korrekte mapper
- **Batch processing**: Håndter mange filer effektivt

## 🐛 Feedback System

Indbygget feedback system til bug reports og feature requests:
- Tilgængeligt på alle sider via floating button
- Gemmer feedback i SQLite database
- Admin interface på `/admin/feedback`

## 🔒 Sikkerhed

- Serverside validering af alle uploads
- Begrænsning på fil antal for at undgå memory issues
- Sikker fil håndtering med tokens
- Ingen sensitive data eksponeret

## 📈 Performance

- **Memory management**: Intelligent håndtering af store filer
- **Batch processing**: Optimeret til mange filer
- **Error resilience**: Graceful handling af fejl
- **User feedback**: Klare beskeder ved problemer

## 🤝 Udvikling

### Tilføj Nye Features
1. Opret ny route i relevant `pages/` modul
2. Tilføj template i `templates/`
3. Opdater navigation i `base.html`
4. Test lokalt med `python main.py`

### Coding Standards
- Python PEP 8 for backend kode
- Responsive CSS design
- Progressive enhancement JavaScript
- Kommenteret kode på dansk

## 📞 Support

For support eller feature requests, brug feedback systemet i applikationen eller opret et issue på GitHub.

## 📄 Licens

Intern brug - Den Gamle By

---

*Udviklet til Den Gamle By's museumsfaglige afdeling* 🏛️