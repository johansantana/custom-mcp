import os
import uuid
from io import BytesIO
from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
# El wrapper de Vercel Blob espera BLOB_READ_WRITE_TOKEN en el entorno [4]
import vercel_blob
# Importamos la clase FastMCP para crear el servidor [1]
from fastmcp import FastMCP

# Cargar variables de entorno del archivo .env [3]
load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Inicializar el cliente de ElevenLabs
# Es buena práctica inicializar clientes que no cambian por cada llamada fuera de la función del 'tool'.
elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Inicializar el servidor FastMCP con un nombre [1, 5]
mcp = FastMCP("ElevenLabs TTS con Vercel Blob")


@mcp.tool
async def use_tts(text: str) -> str:
    """
    Convierte texto a voz usando ElevenLabs, sube el audio a Vercel Blob
    y devuelve la URL del archivo subido.
    """
    if not ELEVENLABS_API_KEY:
        raise ValueError(
            "La clave API de ElevenLabs (ELEVENLABS_API_KEY) no está configurada. Por favor, revisa tu archivo .env [2, 3].")

    # El token BLOB_READ_WRITE_TOKEN debe estar configurado como una variable de entorno [4].
    # La librería `vercel_blob` lo recoge automáticamente.

    # Paso 1: Convertir texto a voz usando ElevenLabs en modo streaming
    # Se utiliza la voz predefinida "Adam" (voice_id="pNInz6obpgDQGcFmaJgB") y
    # el modelo "eleven_turbo_v2_5" para baja latencia [3, 6].
    try:
        audio_stream_response = elevenlabs_client.text_to_speech.stream(
            voice_id="pNInz6obpgDQGcFmaJgB",  # ID de voz predeterminada [3, 6]
            output_format="mp3_22050_32",  # Formato de salida del audio [3, 6]
            text=text,
            # Modelo optimizado para baja latencia [3]
            model_id="eleven_turbo_v2_5",
            voice_settings=VoiceSettings(  # Configuraciones opcionales para personalizar la voz [3, 6]
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
                speed=1.0,
            ),
        )

        # Recopilar los chunks del stream de audio en un objeto BytesIO en memoria
        # para poder leer todos los bytes a la vez para la subida a Vercel Blob [6].
        audio_bytes_io = BytesIO()
        for chunk in audio_stream_response:
            if chunk:
                audio_bytes_io.write(chunk)
        # Restablecer la posición del stream al inicio para su lectura [6]
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
