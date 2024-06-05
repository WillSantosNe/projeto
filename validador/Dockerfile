FROM python:latest

# Para lançar nosso código em Python, devemos importá-lo em nossa imagem.
# Usamos para isso a palavra-chave 'COPY'.
# O primeiro parâmetro, 'main.py', é o nome do arquivo no host.
# O segundo parâmetro, '/', é o caminho onde colocar o arquivo na imagem.
# Aqui, colocamos o arquivo na pasta raiz da imagem.
COPY app.py /

# Precisamos definir o comando para lançar quando rodarmos a imagem.
# Usamos a palavra-chave 'CMD' para isso.
# O comando a seguir executará "python ./main.py".
CMD [ "python", "./app.py" ]
