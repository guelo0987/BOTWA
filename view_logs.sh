#!/bin/bash
# Script para ver logs en tiempo real

LOG_FILE="logs/app.log"

if [ ! -f "$LOG_FILE" ]; then
    echo "⚠️  El archivo de log no existe aún: $LOG_FILE"
    echo "   El servidor debe estar corriendo para generar logs."
    exit 1
fi

echo "📋 Viendo logs en tiempo real..."
echo "   Archivo: $LOG_FILE"
echo "   Presiona Ctrl+C para salir"
echo ""
echo "=========================================="
echo ""

# Seguir el archivo en tiempo real
tail -f "$LOG_FILE"
