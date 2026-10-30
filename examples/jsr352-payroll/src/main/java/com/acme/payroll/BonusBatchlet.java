package com.acme.payroll;

import javax.batch.api.AbstractBatchlet;
import javax.inject.Named;

@Named
public class BonusBatchlet extends AbstractBatchlet {
    @Override public String process() { return "COMPLETED"; }
}
