import os
import uuid
from io import BytesIO
from dotenv import load_dotenv
from openai import OpenAI
import vercel_blob
from fastmcp import FastMCP
from tavily import TavilyClient
import os
import requests
from concurrent.futures import ThreadPoolExecutor


# Cargar variables de entorno del archivo .env [3]
load_dotenv()

# Inicializar el servidor FastMCP con un nombre [1, 5]
mcp = FastMCP("Servidor MCP personalizado para PolyAI")


@mcp.tool
def get_ip_info(ip_address: str):
    """
    Obtiene información de geolocalización para una dirección IP dada.

    Args:
        ip_address: La dirección IP (por ejemplo, "200.88.161.230") a buscar.

    Returns:
        Un diccionario que contiene los datos de geolocalización si la solicitud es exitosa.
        Devuelve None si ocurre un error (por ejemplo, problema de red o IP no válida).
    """
    # Construct the full API URL for the specified IP address.
    url = f"http://ip-api.com/json/{ip_address}"

    try:
        # Send an HTTP GET request to the API endpoint.
        response = requests.get(url)

        # Raise an exception for bad status codes (4xx or 5xx).
        # This will catch errors like "Not Found" or "Internal Server Error".
        response.raise_for_status()

        # Parse the JSON response into a Python dictionary.
        data = response.json()

        # Check if the API itself reported a failure.
        if data.get("status") == "fail":
            print(f"Error from API for IP {ip_address}: {data.get('message')}")
            return None

        return data

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors (e.g., 404, 503).
        print(f"HTTP error occurred: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        # Handle other request-related errors (e.g., network connection issues).
        print(f"An error occurred: {req_err}")
        return None


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializar el cliente de OpenAI
# Es buena práctica inicializar clientes que no cambian por cada llamada fuera de la función del 'tool'.
openai_client = OpenAI(api_key=OPENAI_API_KEY)


@mcp.tool
async def use_tts(text: str, instructions: str = "Read this clearly and professionally") -> str:
    """
    Convierte texto a voz usando OpenAI TTS, sube el audio a Vercel Blob
    y devuelve la URL del archivo subido.
    Parámetros:
      text: El texto a convertir.
      instructions: Instrucciones para controlar el acento, el tono, la impresión, la gama emocional, la entonación, las impresiones, la velocidad del habla, el tono y los susurros. Por defecto: "Read this clearly and professionally".
    """
    if not OPENAI_API_KEY:
        raise ValueError(
            "La clave API de OpenAI (OPENAI_API_KEY) no está configurada. Por favor, revisa tu archivo .env.")

    # El token BLOB_READ_WRITE_TOKEN debe estar configurado como una variable de entorno.
    # La librería `vercel_blob` lo recoge automáticamente.

    try:
        response = openai_client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="nova",  # Una voz femenina clara y profesional
            input=text,
            instructions=instructions
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
        blob_response = vercel_blob.put(
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


@mcp.tool
async def internet_search(query: str) -> dict:
    """
    Realiza una búsqueda en Internet usando la API de Tavily
    y devuelve los resultados encontrados.
    Parámetros:
      query: El texto de búsqueda.
    """
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        raise ValueError(
            "La clave API de Tavily (TAVILY_API_KEY) no está configurada. Por favor, revisa tu archivo .env.")

    try:
        client = TavilyClient(tavily_api_key)
        response = client.search(query=query)

        # Filtrar resultados por score
        high_quality_results = [
            r for r in response["results"] if r["score"] >= 0.9]
        good_quality_results = [
            r for r in response["results"] if r["score"] >= 0.8]

        if high_quality_results:
            # Si hay resultados con score >= 0.9, solo devolver esos
            response["results"] = high_quality_results
        elif good_quality_results:
            # Si no hay resultados >= 0.9 pero hay >= 0.8, devolver esos
            response["results"] = good_quality_results
        # Si no hay ninguno que cumpla los criterios, se mantienen todos los resultados originales

        return response
    except Exception as e:
        print(f"Error al realizar la búsqueda con Tavily: {e}")
        raise ValueError(f"No se pudo completar la búsqueda: {e}")


def fetch_landmark(place_name: str, limit: int):
    """Fetch landmark data from Mapbox Search Box API."""

    # The URL now points to the Search Box API's '/forward' endpoint,
    # which is used for one-off text searches for addresses, places, and POIs[cite: 14, 185].
    url = "https://api.mapbox.com/search/searchbox/v1/forward"

    # The parameters are updated to match the Search Box API.
    # 'q' is the user's query string.
    # 'types' is set to 'poi' to specifically filter for Points of Interest.
    params = {
        "q": place_name,
        "access_token": os.environ.get("MAPBOX_KEY"),
        "limit": limit,
        "types": "poi"
    }

    res = requests.get(url, params=params)
    res.raise_for_status()
    data = res.json()

    # The response is a GeoJSON FeatureCollection, so we parse the 'features' array[cite: 219].
    results = []
    for f in data.get("features", []):
        properties = f.get("properties", {})
        geometry = f.get("geometry", {})

        # Coordinates are in a [longitude, latitude] array within the geometry object.
        coordinates = geometry.get("coordinates", [None, None])

        # 'poi_category' is an array of categories; we take the first one for simplicity.
        categories = properties.get("poi_category")
        category = categories[0] if categories else None

        results.append({
            # The feature's name is in 'properties.name'.
            "name": properties.get("name"),
            # Latitude is the second element of the coordinates array.
            "lat": coordinates[1],
            # Longitude is the first element of the coordinates array.
            "lon": coordinates[0],
            # 'full_address' provides a complete, formatted address string for the feature.
            "address": properties.get("full_address"),
            "category": category,
            # Rating information is not provided by the Search Box API.
            "rating": None
        })

    return results


@mcp.tool
def handle_place_search(mode: str, query: str, limit: int = 1, user_location: dict = None):
    """
    mode: "search_nearby" | "search_landmark" Esto lo eligirás dependiendo qué tipo de solicitud está haciendo el cliente
    limit: Número de resultados a devolver por lugar
    query: cadena de búsqueda (puede contener múltiples nombres de lugares para el modo de punto de referencia). Ejemplo: "Torre Eiffel, Museo del Louvre"
    user_location: {"lat": float, "lon": float} (requerido para search_nearby)
    """

    if mode == "search_nearby":
        if not user_location:
            raise ValueError(
                "user_location is required for search_nearby mode.")

        url = "https://places-api.foursquare.com/places/search"
        headers = {
            "accept": "application/json",
            "X-Places-Api-Version": "2025-06-17",
            "authorization": f"Bearer {os.environ.get('FSQ_API_KEY')}"
        }
        params = {
            "query": query,
            "ll": f"{user_location['lat']},{user_location['lon']}",
            "limit": limit
        }

        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()

        return [
            {
                "name": place.get("name"),
                "lat": place.get("latitude"),
                "lon": place.get("longitude"),
                "address": place.get("location", {}).get("formatted_address"),
                "category": place.get("categories", [{}])[0].get("name") if place.get("categories") else None,
                "rating": None,  # Not included in the API response
                # Adding distance from the query point
                "distance": place.get("distance"),
                # Adding the Foursquare place ID
                "fsq_id": place.get("fsq_place_id"),
                "website": place.get("website"),  # Adding website if available
                "phone": place.get("tel")  # Adding phone number if available
            }
            for place in data.get("results", [])
        ]

    elif mode == "search_landmark":
        # Split the query into multiple place names if separated by commas or "and"
        places = [p.strip() for p in query.replace(
            " and ", ",").split(",") if p.strip()]

        results = []
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(fetch_landmark, place, limit)
                       for place in places]
            for future in futures:
                results.extend(future.result())

        return results

    else:
        raise ValueError(f"Unknown mode: {mode}")


# Ejecutar el servidor FastMCP utilizando el transporte Streamable HTTP [13, 14].
# El host '0.0.0.0' permite que el servidor sea accesible desde cualquier interfaz de red,
# lo cual es útil si planeas desplegarlo en la nube (por ejemplo, en DigitalOcean App Platform) [14, 15].
# El puerto por defecto es 8000 y la ruta '/mcp' [14].
if __name__ == "__main__":
    print("Iniciando servidor FastMCP con transporte Streamable HTTP...")
    # Puedes especificar el host, puerto y ruta según tus necesidades de despliegue [14].
    mcp.run(transport="http", host="0.0.0.0", port=8000, path="/mcp")
