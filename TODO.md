# PharmaSign Backend Implementation TODO

## Phase 1: Project Setup ✅
- [x] requirements.txt
- [x] pyproject.toml
- [x] .gitignore
- [x] .env.example
- [x] manage.py
- [x] pharmasign/__init__.py
- [x] pharmasign/settings.py
- [x] pharmasign/urls.py
- [x] pharmasign/asgi.py
- [x] pharmasign/wsgi.py

## Phase 2: Core Apps - common & accounts ✅
- [x] common app structure (models.py mixins, utils.py, choices.py)
- [x] accounts app (custom User model, serializers, auth views)
- [x] settings/urls updated for apps

## Phase 3: Domain Apps & Models [ ]
- [ ] organizations app (models/serializers/admin)
- [ ] patients app (Enrollment/Profile/MedicalInfo/Session)
- [ ] pharmacies app (Pharmacy/PharmacistProfile)
- [ ] prescriptions app (Prescription/Item/AccessLog)
- [ ] Permissions classes

## Phase 4: Views/URLs/Services [ ]
- [ ] ViewSets & custom actions per endpoint spec
- [ ] App urls.py & main router
- [ ] Services (QR gen, account from enrollment, session start, summary)

## Phase 5: Finalization [ ]
- [ ] Migrations
- [ ] Minimal tests
- [ ] Admin registrations

## Phase 6: Docs [ ]
- [ ] README.md

*Phase 2 progress: common & User model done. Next: accounts serializers/views. pip install ongoing.*

