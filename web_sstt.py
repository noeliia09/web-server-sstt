# coding=utf-8
#!/usr/bin/env python3

import socket
import selectors    #https://docs.python.org/3/library/selectors.html
import select
import types        # Para definir el tipo de datos data
import argparse     # Leer parametros de ejecución
import os           # Obtener ruta y extension
from datetime import datetime, timedelta # Fechas de los mensajes HTTP
import time         # Timeout conexión
import sys          # sys.exit
import re           # Analizador sintáctico
import logging      # Para imprimir logs

#serviciostelematicos9448.com

BUFSIZE = 8192 # Tamaño máximo del buffer que se puede utilizar
TIMEOUT_CONNECTION = 35 #10+9+4+4+8 # Timout para la conexión persistente
MAX_ACCESOS = 10

# Extensiones admitidas (extension, name in HTTP)
filetypes = {"gif":"image/gif", "jpg":"image/jpg", "jpeg":"image/jpeg", "png":"image/png", "htm":"text/htm", 
             "html":"text/html", "css":"text/css", "js":"text/js"}

# Configuración de logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s.%(msecs)03d] [%(levelname)-7s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()


def enviar_mensaje(cs, data):
    """ Esta función envía datos (data) a través del socket cs
        Devuelve el número de bytes enviados.
    """
    return cs.send(data.encode())


def recibir_mensaje(cs):
    """ Esta función recibe datos a través del socket cs
        Leemos la información que nos llega. recv() devuelve un string con los datos.
    """
    return cs.recv(BUFSIZE).decode()



def cerrar_conexion(cs):
    """ Esta función cierra una conexión activa.
    """
    cs.close(); 


def process_cookies(headers,  cs):
    """ Esta función procesa la cookie cookie_counter
        1. Se analizan las cabeceras en headers para buscar la cabecera Cookie
        2. Una vez encontrada una cabecera Cookie se comprueba si el valor es cookie_counter
        3. Si no se encuentra cookie_counter , se devuelve 1
        4. Si se encuentra y tiene el valor MAX_ACCESSOS se devuelve MAX_ACCESOS
        5. Si se encuentra y tiene un valor 1 <= x < MAX_ACCESOS se incrementa en 1 y se devuelve el valor
    """
    for cabecera in headers:
        nombre = cabecera.split(": ")[0]
        if nombre == "Cookie":
            cookie_counter = int(cabecera.split("=")[1])
            if cookie_counter == MAX_ACCESOS:
                return MAX_ACCESOS
            else:
                return cookie_counter + 1
    return 1





def process_web_request(cs, webroot):
    """ Procesamiento principal de los mensajes recibidos.
        Típicamente se seguirá un procedimiento similar al siguiente (aunque el alumno puede modificarlo si lo desea)

        * Bucle para esperar hasta que lleguen datos en la red a través del socket cs con select()

            * Se comprueba si hay que cerrar la conexión por exceder TIMEOUT_CONNECTION segundos
              sin recibir ningún mensaje o hay datos. Se utiliza select.select

            * Si no es por timeout y hay datos en el socket cs.
                * Leer los datos con recv.
                * Analizar que la línea de solicitud y comprobar está bien formateada según HTTP 1.1
                    * Devuelve una lista con los atributos de las cabeceras.
                    * Comprobar si la versión de HTTP es 1.1
                    * Comprobar si es un método GET o POST. Si no devolver un error Error 405 "Method Not Allowed".
                    * Leer URL y eliminar parámetros si los hubiera
                    * Comprobar si el recurso solicitado es /, En ese caso el recurso es index.html
                    * Construir la ruta absoluta del recurso (webroot + recurso solicitado)
                    * Comprobar que el recurso (fichero) existe, si no devolver Error 404 "Not found"
                    * Analizar las cabeceras. Imprimir cada cabecera y su valor. Si la cabecera es Cookie comprobar
                      el valor de cookie_counter para ver si ha llegado a MAX_ACCESOS.
                      Si se ha llegado a MAX_ACCESOS devolver un Error "403 Forbidden"
                    * Obtener el tamaño del recurso en bytes.
                    * Extraer extensión para obtener el tipo de archivo. Necesario para la cabecera Content-Type
                    * Preparar respuesta con código 200. Construir una respuesta que incluya: la línea de respuesta y
                      las cabeceras Date, Server, Connection, Set-Cookie (para la cookie cookie_counter),
                      Content-Length y Content-Type.
                    * Leer y enviar el contenido del fichero a retornar en el cuerpo de la respuesta.
                    * Se abre el fichero en modo lectura y modo binario
                        * Se lee el fichero en bloques de BUFSIZE bytes (8KB)
                        * Cuando ya no hay más información para leer, se corta el bucle

            * Si es por timeout, se cierra el socket tras el período de persistencia.
                * NOTA: Si hay algún error, enviar una respuesta de error con una pequeña página HTML que informe del error.
    """
    while True:
        rlist = [cs]
        rsublist, _, _ = select.select(rlist,[],[],TIMEOUT_CONNECTION)
        if rsublist:
            data = recibir_mensaje(cs).split("\r\n")
            linea_solicitud = data[0]
            cabeceras = data[1:]

            if len(linea_solicitud.split()) == 3:
                metodo = linea_solicitud.split()[0]
                url = linea_solicitud.split()[1]
                version = linea_solicitud.split()[2]
                if version == "HTTP/1.1":
                    if metodo in ['GET', 'POST']:
                        recurso, _, parametros = url.partition("?")
                        if recurso == "/":
                            recurso = "/index.html"
                        for par in parametros.split("&"):
                            nombre, _, valor = par.partition("=")
                            if nombre == "email":
                                dominio = valor.split("%40")[-1]
                                if dominio == "um.es":
                                    recurso = "/EmailCorrecto.html"
                                else:
                                    recurso = "/EmailIncorrecto.html" 
                        ruta = webroot+recurso
                        if os.path.isfile(ruta):
                            if process_host(cabeceras):
                                codigo = "200"
                                tamano = os.stat(ruta).st_size
                                tipo = filetypes.get(ruta.split(".")[-1])
                                fecha = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
                                if url == "/index.html":
                                    cookie_counter = process_cookies(cabeceras, cs)
                                    if cookie_counter != MAX_ACCESOS:
                                        condicion = True
                                    else:    
                                        codigo = "403 Forbidden"
                                else:
                                    cookie_counter = None
                                    condicion = False  
                            else: 
                                codigo = "400 Bad Request"   
                        else:
                            codigo = "404 Not Found"
                    else:
                        codigo = "405 Method Not Allowed"
                else:
                    codigo = "505 HTTP Version Not Supported"   
            else:
                codigo = "400 Bad Request"

            if codigo == "200":
                enviar_mensaje(cs, mensaje(codigo, tipo, tamano, fecha, cookie_counter, condicion))
                with open(ruta, "rb") as f:
                    while True:
                        bloque = f.read(BUFSIZE)
                        if not bloque:
                            break
                        cs.send(bloque)
            else:
                codigo = codigo.split()[0]
                with open(codigo + ".html", "rb") as f:
                        cuerpo = f.read()
                        tamano = len(cuerpo)
                        tipo= "text/html"
                        enviar_mensaje(cs, mensaje(codigo, tipo, tamano, fecha, None, False))
                        cs.send(cuerpo)
        else:
            cerrar_conexion(cs)
            return None
            # Termino por TimeOut


def mensaje(codigo, tipo, tamano, fecha, cookie, condicion):
    if codigo == "200":
        if condicion:
            respuesta = f"HTTP/1.1 200 OK\r\nDate: {fecha}\r\nServer: web_sstt\r\nConnection: keep-alive\r\nKeep-Alive: {TIMEOUT_CONNECTION}\r\nSet-Cookie: cookie_counter_9448={cookie}; Max-Age=30\r\nContent-Length: {tamano}\r\nContent-Type: {tipo}\r\n\r\n"
        else:
            respuesta = f"HTTP/1.1 200 OK\r\nDate: {fecha}\r\nServer: web_sstt\r\nConnection: keep-alive\r\nKeep-Alive: {TIMEOUT_CONNECTION}\r\nContent-Length: {tamano}\r\nContent-Type: {tipo}\r\n\r\n"
    else:
        respuesta = f"HTTP/1.1 {codigo}\r\nConnection: close\r\nDate: {fecha}\r\nServer: web_sstt\r\nContent-Length: {tamano}\r\nContent-Type: {tipo}\r\n\r\n"
    return respuesta

def process_host(headers):
    for cabecera in headers:
        nombre = cabecera.split(": ")[0]
        if nombre == "Host":
            return True
    return False

def main():
    """ Función principal del servidor
    """
    
    try:

        # Argument parser para obtener la ip y puerto de los parámetros de ejecución del programa. IP por defecto 0.0.0.0
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--port", help="Puerto del servidor", type=int, required=True)
        parser.add_argument("-ip", "--host", help="Dirección IP del servidor o localhost", required=True)
        parser.add_argument("-wb", "--webroot", help="Directorio base desde donde se sirven los ficheros (p.ej. /home/user/mi_web)")
        parser.add_argument('--verbose', '-v', action='store_true', help='Incluir mensajes de depuración en la salida')
        args = parser.parse_args()


        if args.verbose:
            logger.setLevel(logging.DEBUG)

        logger.info('Enabling server in address {} and port {}.'.format(args.host, args.port))

        logger.info("Serving files from {}".format(args.webroot))

        """ Funcionalidad a realizar
        * Crea un socket TCP (SOCK_STREAM)
        * Permite reusar la misma dirección previamente vinculada a otro proceso. Debe ir antes de sock.bind
        * Vinculamos el socket a una IP y puerto elegidos

        * Escucha conexiones entrantes

        * Bucle infinito para mantener el servidor activo indefinidamente
            - Aceptamos la conexión

            - Creamos un proceso hijo

            - Si es el proceso hijo se cierra el socket del padre y procesar la petición con process_web_request()

            - Si es el proceso padre cerrar el socket que gestiona el hijo.
        """
        cs = socket.socket(socket.AF_INET,socket.SOCK_STREAM,0)
        cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cs.bind((args.host, args.port))
        cs.listen(64)
        while True:
            conn,addr = cs.accept()
            pid = os.fork()
            if pid == 0:
                cerrar_conexion(cs)
                process_web_request(conn, args.webroot)
            else:
                cerrar_conexion(conn)

    except KeyboardInterrupt:
        True

if __name__== "__main__":
    main()
