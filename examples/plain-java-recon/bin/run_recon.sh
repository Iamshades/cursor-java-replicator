#!/bin/sh
java -Ddb.url=$DB_URL -cp lib/recon.jar com.acme.recon.ReconMain "$1" || exit 3
