# Consulta de Preço PDF — v2

Alterações desta versão:

- Cabeçalho corrigido: não aparece mais duplicado e fica alinhado com as colunas.
- Ao clicar em Copiar, o código é copiado sem zeros à esquerda:
  - 00000118 -> 118
  - 00001669 -> 1669
- Cada cópia reduz 1 unidade da Qtd.
- Quando Qtd chega a 0, o botão Copiar fica desabilitado.
- Nunca permite quantidade negativa.
- O contador de cópias continua registrando quantas vezes cada produto foi copiado.
- A quantidade reduzida permanece reduzida enquanto o PDF estiver carregado.

Para testar:
1. pip install -r requirements.txt
2. python app.py

Para gerar o EXE:
1. Execute build.bat
2. Pegue dist\ConsultaPrecoPDF.exe
