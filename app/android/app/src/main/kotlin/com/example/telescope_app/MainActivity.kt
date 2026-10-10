package com.example.telescope_app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Modo campo: entrar no WiFi do próprio telescópio SÓ DENTRO DESTE APP.
 *
 * Esse WiFi não tem internet. Entrando nele pelas configurações do celular, o Android tende a
 * voltar para o 4G e o app perde o telescópio. Aqui o sistema liga a rede para este processo
 * (WifiNetworkSpecifier + bindProcessToNetwork, Android 10 em diante): o resto do celular segue
 * na internet. O Android mostra o próprio aviso pedindo a permissão de quem usa.
 *
 * Canal "telescope/wifi" (lado Dart: lib/data/telescope_wifi.dart):
 *   join(ssid, psk) -> "joined" | "unavailable" | "unsupported"
 *   leave()
 *
 * ESTADO: escrito conforme a documentação do Android; ainda NÃO validado num celular (depende
 * de a Jetson estar em modo ponto de acesso). Ver app/docs/03-conexao.md.
 */
class MainActivity : FlutterActivity() {
    private var callback: ConnectivityManager.NetworkCallback? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "telescope/wifi")
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "join" -> join(call.argument<String>("ssid") ?: "", call.argument<String>("psk") ?: "", result)
                    "leave" -> {
                        leave()
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    override fun onDestroy() {
        leave()
        super.onDestroy()
    }

    private fun connectivity() = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    private fun join(ssid: String, psk: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || ssid.isEmpty()) {
            result.success("unsupported")
            return
        }
        leave()
        val specifier = WifiNetworkSpecifier.Builder().setSsid(ssid)
            .apply { if (psk.isNotEmpty()) setWpa2Passphrase(psk) }
            .build()
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            // a rede do telescópio não tem internet, e é isso mesmo que queremos
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(specifier)
            .build()
        var answered = false
        fun answer(value: String) {
            runOnUiThread {
                if (!answered) {
                    answered = true
                    result.success(value)
                }
            }
        }
        val network = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                // daqui em diante as conexões DESTE processo saem pelo WiFi do telescópio
                connectivity().bindProcessToNetwork(network)
                answer("joined")
            }

            // a pessoa fechou o aviso, ou a rede não apareceu: o Android não diz qual dos dois
            override fun onUnavailable() = answer("unavailable")

            override fun onLost(network: Network) {
                connectivity().bindProcessToNetwork(null)
            }
        }
        callback = network
        try {
            connectivity().requestNetwork(request, network, 60_000)
        } catch (e: SecurityException) {
            callback = null
            answer("unavailable")
        }
    }

    private fun leave() {
        val current = callback ?: return
        callback = null
        connectivity().bindProcessToNetwork(null)
        try {
            connectivity().unregisterNetworkCallback(current)
        } catch (e: IllegalArgumentException) {
            // já não estava registrado
        }
    }
}
