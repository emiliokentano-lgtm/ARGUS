package main

import "testing"

// Der Dienst darf ohne Konfiguration nicht starten - ein Konnektor mit
// falscher connector_id meldet seine Metriken unter dem falschen Namen.
func TestRunFailsWithoutConfiguration(t *testing.T) {
	t.Setenv("ARGUS_CONNECTOR_ID", "")
	t.Setenv("ARGUS_SOURCE_ID", "aisstream")
	if err := run(); err == nil {
		t.Fatal("run() haette ohne ARGUS_CONNECTOR_ID fehlschlagen muessen")
	}
}
