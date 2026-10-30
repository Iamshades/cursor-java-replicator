#!/bin/sh
# Called by Control-M job INVEXP01
java -Xmx1g -jar /opt/apps/legacy-invoice-batch.jar --spring.batch.job.names=invoiceExportJob businessDate=$1
