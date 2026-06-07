-- V2__add_categoria.sql
-- Adiciona tabela de categorias e vincula à receita

CREATE TABLE IF NOT EXISTS categoria (
    codigo      VARCHAR(20)  PRIMARY KEY,
    descricao   VARCHAR(100) NOT NULL
);

INSERT INTO categoria (codigo, descricao) VALUES
    ('SOBREMESA',      'Sobremesas e doces em geral'),
    ('SALGADO',        'Salgados e lanches'),
    ('PRATO',          'Pratos principais'),
    ('ACOMPANHAMENTO', 'Acompanhamentos e guarnições')
ON CONFLICT (codigo) DO NOTHING;

ALTER TABLE receita
    ADD COLUMN IF NOT EXISTS categoria_codigo VARCHAR(20)
    REFERENCES categoria(codigo);