CREATE TABLE invoice (id NUMBER PRIMARY KEY, customer_id NUMBER, amount NUMBER(12,2), currency CHAR(3), status VARCHAR2(20), issued_on DATE);
