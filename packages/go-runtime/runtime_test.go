package runtime

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestLoadConfigRequiresConnectorID(t *testing.T) {
	t.Setenv("ARGUS_CONNECTOR_ID", "")
	t.Setenv("ARGUS_SOURCE_ID", "aisstream")
	if _, err := LoadConfig(); err == nil {
		t.Fatal("ein Dienst ohne ARGUS_CONNECTOR_ID darf nicht starten")
	}
}

func TestLoadConfigRequiresSourceID(t *testing.T) {
	t.Setenv("ARGUS_CONNECTOR_ID", "ingest-sea")
	t.Setenv("ARGUS_SOURCE_ID", "")
	if _, err := LoadConfig(); err == nil {
		t.Fatal("ein Dienst ohne ARGUS_SOURCE_ID darf nicht starten")
	}
}

func TestLoadConfigDefaults(t *testing.T) {
	t.Setenv("ARGUS_CONNECTOR_ID", "ingest-sea")
	t.Setenv("ARGUS_SOURCE_ID", "aisstream")
	t.Setenv("ARGUS_NATS__URL", "")
	t.Setenv("ARGUS_METRICS__PORT", "")
	cfg, err := LoadConfig()
	if err != nil {
		t.Fatalf("unerwarteter Fehler: %v", err)
	}
	if cfg.NatsURL != "nats://localhost:4222" {
		t.Errorf("NatsURL = %q, erwartet den Standardwert", cfg.NatsURL)
	}
	if cfg.MetricsPort != 9100 {
		t.Errorf("MetricsPort = %d, erwartet 9100", cfg.MetricsPort)
	}
}

func TestLoadConfigRejectsInvalidPort(t *testing.T) {
	t.Setenv("ARGUS_CONNECTOR_ID", "ingest-sea")
	t.Setenv("ARGUS_SOURCE_ID", "aisstream")
	for _, port := range []string{"keine-zahl", "0", "70000"} {
		t.Setenv("ARGUS_METRICS__PORT", port)
		if _, err := LoadConfig(); err == nil {
			t.Errorf("Port %q haette abgelehnt werden muessen", port)
		}
	}
}

func TestHealthAndReadinessAreSeparate(t *testing.T) {
	// Ein angehaltener Konnektor lebt, ist aber nicht bereit - genau diese
	// Unterscheidung braucht der Kill-Switch.
	ready := false
	hs := NewHealthServer(0, func() bool { return ready })

	rec := httptest.NewRecorder()
	hs.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/healthz", nil))
	if rec.Code != http.StatusOK {
		t.Errorf("healthz = %d, erwartet 200", rec.Code)
	}

	rec = httptest.NewRecorder()
	hs.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("readyz = %d, erwartet 503 solange nicht bereit", rec.Code)
	}

	ready = true
	rec = httptest.NewRecorder()
	hs.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if rec.Code != http.StatusOK {
		t.Errorf("readyz = %d, erwartet 200 sobald bereit", rec.Code)
	}
}
