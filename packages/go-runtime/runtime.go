// Package runtime enthaelt das, was jeder Go-Dienst in ARGUS braucht:
// Konfiguration aus der Umgebung, einen Health-Endpunkt und ein sauberes
// Herunterfahren.
//
// Die Go-Dienste sind die Hochlast-Konnektoren (AIS, ADS-B). Sie folgen
// denselben Betriebsregeln wie das Python-SDK - insbesondere: bei SIGTERM
// wird der laufende Batch zu Ende gefuehrt, nicht abgeschnitten.
package runtime

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

// Config ist die Grundkonfiguration jedes Dienstes. Werte kommen
// ausschliesslich aus der Umgebung (Definition of Done, Punkt 5).
type Config struct {
	ConnectorID string
	SourceID    string
	NatsURL     string
	MetricsPort int
	// Frist, die einem laufenden Batch beim Herunterfahren bleibt.
	ShutdownGrace time.Duration
}

// LoadConfig liest die Konfiguration aus der Umgebung.
//
// Fehlende Pflichtwerte sind ein Fehler und kein Standardwert: ein Dienst,
// der ohne connector_id startet, meldet seine Metriken unter dem falschen
// Namen und faellt erst Wochen spaeter auf.
func LoadConfig() (Config, error) {
	cfg := Config{
		ConnectorID:   os.Getenv("ARGUS_CONNECTOR_ID"),
		SourceID:      os.Getenv("ARGUS_SOURCE_ID"),
		NatsURL:       envOr("ARGUS_NATS__URL", "nats://localhost:4222"),
		MetricsPort:   9100,
		ShutdownGrace: 30 * time.Second,
	}
	if cfg.ConnectorID == "" {
		return cfg, errors.New("ARGUS_CONNECTOR_ID ist nicht gesetzt")
	}
	if cfg.SourceID == "" {
		return cfg, errors.New("ARGUS_SOURCE_ID ist nicht gesetzt")
	}
	if raw := os.Getenv("ARGUS_METRICS__PORT"); raw != "" {
		port, err := strconv.Atoi(raw)
		if err != nil {
			return cfg, fmt.Errorf("ARGUS_METRICS__PORT ist keine Zahl: %q", raw)
		}
		if port < 1 || port > 65535 {
			return cfg, fmt.Errorf("ARGUS_METRICS__PORT liegt ausserhalb 1..65535: %d", port)
		}
		cfg.MetricsPort = port
	}
	return cfg, nil
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

// HealthServer stellt /healthz und /readyz bereit.
//
// Getrennt, weil sie verschiedene Fragen beantworten: healthz heisst "der
// Prozess lebt", readyz heisst "der Dienst kann arbeiten". Ein Konnektor, der
// ueber den Kill-Switch angehalten wurde, ist gesund, aber nicht bereit.
type HealthServer struct {
	server *http.Server
	ready  func() bool
}

// NewHealthServer erzeugt den Server. ready wird bei jeder Anfrage neu
// ausgewertet.
func NewHealthServer(port int, ready func() bool) *HealthServer {
	mux := http.NewServeMux()
	hs := &HealthServer{ready: ready}
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if hs.ready != nil && !hs.ready() {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte("nicht bereit"))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("bereit"))
	})
	hs.server = &http.Server{
		Addr:              fmt.Sprintf(":%d", port),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	return hs
}

// Handler gibt den Mux zurueck, damit er in Tests ohne offenen Port
// benutzt werden kann.
func (h *HealthServer) Handler() http.Handler { return h.server.Handler }

// Start laesst den Server im Hintergrund laufen.
func (h *HealthServer) Start() {
	go func() {
		if err := h.server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			fmt.Fprintf(os.Stderr, "Health-Server beendet: %v\n", err)
		}
	}()
}

// Shutdown faehrt den Server innerhalb der Frist herunter.
func (h *HealthServer) Shutdown(ctx context.Context) error {
	return h.server.Shutdown(ctx)
}

// SignalContext liefert einen Kontext, der bei SIGTERM oder SIGINT abbricht.
//
// Damit gilt fuer Go-Dienste dasselbe wie fuer die Python-Konnektoren: das
// Signal beendet nicht den Prozess, sondern loest ein geordnetes Ende aus.
func SignalContext() (context.Context, context.CancelFunc) {
	return signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
}
