package com.acme.recon;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;

public class ReconMain {
    public static void main(String[] args) throws Exception {
        String file = args[0];
        try (Connection c = DriverManager.getConnection(System.getProperty("db.url"))) {
            c.setAutoCommit(false);
            PreparedStatement ps = c.prepareStatement("INSERT INTO recon_result (txn_id, status) VALUES (?, ?)");
            int n = 0;
            for (String line : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(file))) {
                ps.setString(1, line.split(",")[0]);
                ps.setString(2, "MATCHED");
                ps.executeUpdate();
                if (++n % 1000 == 0) c.commit();
            }
            c.commit();
        }
        System.exit(0);
    }
}
