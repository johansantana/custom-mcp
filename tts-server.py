import os
import uuid
from io import BytesIO
from dotenv import load_dotenv
from openai import OpenAI
# El wrapper de Vercel Blob espera BLOB_READ_WRITE_TOKEN en el entorno [4]
import vercel_blob
# Importamos la clase FastMCP para crear el servidor [1]
from fastmcp import FastMCP

# Cargar variables de entorno del archivo .env [3]
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializar el cliente de OpenAI
# Es buena práctica inicializar clientes que no cambian por cada llamada fuera de la función del 'tool'.
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Inicializar el servidor FastMCP con un nombre [1, 5]
mcp = FastMCP("ElevenLabs TTS con Vercel Blob")


@mcp.tool
async def use_tts(text: str) -> str:
    """
    Convierte texto a voz usando OpenAI TTS, sube el audio a Vercel Blob
    y devuelve la URL del archivo subido.
    """
    if not OPENAI_API_KEY:
        raise ValueError(
            "La clave API de OpenAI (OPENAI_API_KEY) no está configurada. Por favor, revisa tu archivo .env.")

    # El token BLOB_READ_WRITE_TOKEN debe estar configurado como una variable de entorno.
    # La librería `vercel_blob` lo recoge automáticamente.

    # Paso 1: Convertir texto a voz usando OpenAI TTS
    # Se utiliza el modelo TTS-1 con la voz "alloy"
    try:
        response = openai_client.audio.speech.create(
            model="tts-1",
            voice="nova",  # Una voz femenina clara y profesional
            input=text
        )

        # Obtener los bytes del audio
        audio_bytes_io = BytesIO(response.content)
        # Restablecer la posición del stream al inicio para su lectura
        audio_bytes_io.seek(0)

    except Exception as e:
        print(f"Error al convertir texto a voz con ElevenLabs: {e}")
        raise ValueError(f"No se pudo generar el audio: {e}")

    # Paso 2: Subir el audio a Vercel Blob Storage
    # Generar un nombre de archivo único utilizando UUID para evitar sobrescribir archivos existentes [7, 8].
    blob_filename = f"audio_{uuid.uuid4()}.mp3"

    try:
        # El método `put` de `vercel_blob` toma el nombre del archivo y los bytes del archivo [9].
        # Se usa `multipart=True` para archivos grandes, lo que mejora la resiliencia contra problemas de red [7, 9].
        # El parámetro `verbose=True` mostrará información detallada del progreso durante la subida [7, 9-11].
        # Nota: El método `put` de `vercel_blob` es asíncrono, por lo tanto, se utiliza `await`.
        blob_response = await vercel_blob.put(
            blob_filename,
            # Se leen todos los bytes del stream de audio.
            audio_bytes_io.read(),
            multipart=True,
            verbose=True
        )
        # La respuesta del método `put` contiene la URL del archivo subido [7, 12].
        uploaded_url = blob_response['url']
        return uploaded_url
    except Exception as e:
        print(f"Error al subir el audio a Vercel Blob: {e}")
        raise ValueError(f"No se pudo subir el archivo a Vercel Blob: {e}")

# Ejecutar el servidor FastMCP utilizando el transporte Streamable HTTP [13, 14].
# El host '0.0.0.0' permite que el servidor sea accesible desde cualquier interfaz de red,
# lo cual es útil si planeas desplegarlo en la nube (por ejemplo, en DigitalOcean App Platform) [14, 15].
# El puerto por defecto es 8000 y la ruta '/mcp' [14].
if __name__ == "__main__":
    print("Iniciando servidor FastMCP con transporte Streamable HTTP...")
    # Puedes especificar el host, puerto y ruta según tus necesidades de despliegue [14].
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")
