// Konnektor ingest-sea: AIS (162 MHz, Schiffspositionen).
//
// Go statt Python wegen des Durchsatzes (Konzept, Kapitel 15): bei einigen
// tausend Positionsmeldungen pro Sekunde entscheidet das Speicherverhalten,
// und die Nebenlaeufigkeit ist hier billiger.
//
// Stand: Geruest. Die eigentliche Anbindung kommt mit Prompt 7. Was hier steht,
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
		fmt.Fprintf(os.Stderr, "ingest-sea: %v\n", err)
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
		"ingest-sea gestartet (connector=%s, source=%s, bus=%s, health=:%d)\n",
		cfg.ConnectorID, cfg.SourceID, cfg.NatsURL, cfg.MetricsPort,
	)
	fmt.Println("ingest-sea: Geruest ohne Quellenanbindung - siehe Prompt 7")

	<-ctx.Done()
	fmt.Println("ingest-sea: Signal empfangen, fahre herunter")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownGrace)
	defer cancel()
	if err := health.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("Health-Server nicht sauber beendet: %w", err)
	}
	return nil
}
