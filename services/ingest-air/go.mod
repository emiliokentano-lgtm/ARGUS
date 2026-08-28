module github.com/emiliokentano-lgtm/argus/services/ingest-air

go 1.24

require github.com/emiliokentano-lgtm/argus/packages/go-runtime v0.0.0

// Das Laufzeitpaket ist nicht veroeffentlicht. go.work verbindet die Module
// beim Bauen; der replace-Eintrag sorgt dafuer, dass das Modul auch OHNE
// Workspace aufloest - etwa wenn ein Werkzeug es einzeln betrachtet oder
// 'go mod download' den Modulgraphen abarbeitet.
replace github.com/emiliokentano-lgtm/argus/packages/go-runtime => ../../packages/go-runtime
