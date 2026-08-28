// Konnektor ingest-air: ADS-B (1090 MHz, Flugzeugpositionen).
//
// Go statt Python wegen des Durchsatzes (Konzept, Kapitel 15): bei einigen
// tausend Positionsmeldungen pro Sekunde entscheidet das Speicherverhalten,
// und die Nebenlaeufigkeit ist hier billiger.
//
// Stand: Geruest. Die eigentliche Anbindung kommt mit Prompt 8/9. Was hier steht,
// ist der Rahmen, den jeder Dienst braucht - Konfiguration, Health-Endpunkte,
// geordnetes Herunterfahren - und der nicht in jedem Dienst neu erfunden wird.
package main

import (
	"context"
	"fmt"
	"os"

	runtime "github.com/emiliokentano-lgtm/argus/packages/go-runtime"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "ingest-air: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := runtime.LoadConfig()
	if err != nil {
		return fmt.Errorf("Konfiguration unvollstaendig: %w", err)
	}

	ctx, stop := runtime.SignalContext()
	defer stop()

	// Solange der Dienst noch nicht anbindet, ist er gesund, aber nicht
	// bereit. Das ist ehrlicher als ein readyz, das Bereitschaft meldet, die
	// es nicht gibt.
	health := runtime.NewHealthServer(cfg.MetricsPort, func() bool { return false })
	health.Start()

	fmt.Printf(
		"ingest-air gestartet (connector=%s, source=%s, bus=%s, health=:%d)\n",
		cfg.ConnectorID, cfg.SourceID, cfg.NatsURL, cfg.MetricsPort,
	)
	fmt.Println("ingest-air: Geruest ohne Quellenanbindung - siehe Prompt 8/9")

	<-ctx.Done()
	fmt.Println("ingest-air: Signal empfangen, fahre herunter")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownGrace)
	defer cancel()
	if err := health.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("Health-Server nicht sauber beendet: %w", err)
	}
	return nil
}
