# Le guide de kealeb

Tout ce que le cadriciel sait faire, dans l'ordre où vous le rencontrerez.
Une demi-heure d'un bout à l'autre. Chaque extrait ci-dessous compile ; les
versions longues sont dans [`examples/`](../examples).

*The same walkthrough in English: [`guide.md`](guide.md).*

---

## 1. Un programme

```keal
import "kealeb/kealeb.keal"

val site = app("Mon site")

site.page("/", { req -> column([
    h1("Bonjour"),
    p("depuis Keal")
])})

site.run(8080)
```

```sh
tools/build.sh bonjour.keal
build/bonjour
```

`app(titre)` crée une application. `run(port)` sert jusqu'à l'arrêt du
processus. Entre ces deux lignes, on déclare ce que le site répond.

L'import est le parapluie : tout ce guide est visible après cette ligne. Un
programme qui en veut moins importe un seul module —
`import "kealeb/src/http.keal"` amène la requête et la réponse, et rien
d'autre.

## 2. Les routes

Cinq verbes et un attrape-tout, chacun prenant un chemin et un gestionnaire :

```keal
site.get("/sante", { req -> text("ok") })
site.post("/commandes", { req -> jsonBody("{\"id\":7}").status(201) })
site.put("/commandes/{id}", { req -> text("remplacée ${req.param("id")}") })
site.patch("/commandes/{id}", { req -> text("modifiée") })
site.delete("/commandes/{id}", { req -> noContent() })
site.any("/ping", { req -> text("pong") })
```

Un gestionnaire est un `(Request) -> Response`. C'est un type de fonction
ordinaire, donc ce peut être une lambda, ou une valeur tenue dans une variable
et qu'on se passe :

```keal
val sante = { req: Request -> text("ok") }

site.get("/sante", sante)
site.get("/santez", sante)
```

Une `func` **nommée** serait la chose évidente à écrire ici, et cela ne marche
pas encore : `keal build` mécompile une fonction nommée utilisée comme valeur
— il passe un pointeur de fonction nu là où une fermeture est attendue, et le
programme meurt. La VM à octets, elle, a bon, et c'est ainsi que le défaut a
été trouvé. En attendant la correction du compilateur, tenez un gestionnaire
dans un `val` comme ci-dessus. C'est signalé en amont, et c'est le seul
endroit de ce guide où la forme est décidée par le langage et non par le
cadriciel.

### Ce qu'un motif peut dire

| motif | correspond à | `req.param(...)` |
|---|---|---|
| `/user/new` | exactement cela | — |
| `/user/{id}` | `/user/42` | `id` vaut `42` |
| `/files/{reste...}` | `/files/a/b.css` | `reste` vaut `a/b.css` |

Un `{nom...}` final attrape tout ce qui reste, barres obliques comprises, et
ne peut être que le dernier. Les segments arrivent décodés :
`/user/le%20monde` donne `req.param("id") == "le monde"`.

**Quand deux motifs correspondent, celui qui a le plus de segments littéraux
gagne.** `/user/new` l'emporte sur `/user/{id}`, quel que soit l'ordre de
déclaration. C'est la seule règle de priorité, et elle ne dépend pas de
l'ordre où vous les avez écrites.

Un chemin qui ne correspond à rien est un 404. Un chemin qui correspond sous
un autre verbe est un **405** portant `Allow:` — la différence compte pour
tous les clients, et un cadriciel incapable de la faire les oblige tous à
deviner.

## 3. La requête

```keal
site.post("/recherche", { req ->
    val q = req.queryOr("q", "")                 // ?q=…
    val page = req.queryOr("page", "1").toInt() ?: 1
    val qui = req.headerOr("user-agent", "?")    // la casse est indifférente
    val sid = req.cookie("session")              // String?
    val form = req.form()                        // un formulaire posté, décodé
    val corps = req.text()                       // le corps, en texte
    text("${q} ${page} ${qui}")
})
```

| | |
|---|---|
| `method` `path` `target` `version` `peer` | tels qu'arrivés ; `path` est décodé, `target` non |
| `param(nom)` | ce que la route a capturé — `""` si la route n'a pas ce trou |
| `query` · `queryOr(nom, défaut)` | la chaîne de requête, analysée |
| `header(nom): String?` · `headerOr` · `hasHeader` | la casse est repliée ; un en-tête envoyé deux fois arrive joint par `, ` |
| `cookies(): Map` · `cookie(nom): String?` | |
| `text()` · `form()` · `formAll()` · `body` | le corps en texte, en formulaire, en gardant les répétitions, en octets |
| `contentType()` | le type de média, sans ses paramètres |
| `keepAlive()` · `isUpgrade()` | ce à quoi sert la connexion |

Une `Request` ne se modifie pas. Keal dit que le contenu d'un paramètre
appartient à l'appelant sauf si la signature dit `var`, et un type de fonction
ne peut pas dire `var` — donc un gestionnaire reçoit la réponse plutôt que
l'occasion de changer la question. Là où le cadriciel doit ajouter quelque
chose, il en construit une nouvelle : c'est ce que fait `withParams`, et elle
partage le corps au lieu de le copier.

## 4. La réponse

```keal
html("<p>salut</p>")                     // text/html; charset=utf-8
text("brut")                             // text/plain; charset=utf-8
jsonBody("{\"ok\":true}")                // application/json
bytes("image/png", unBuf)                // n'importe quoi, depuis des octets
noContent()                              // 204
redirect("/suite")                       // 302 ; redirect("/x", 301) si permanent
notFound("commande inconnue")            // 404
badRequest("id doit être un nombre")     // 400
serverError()                            // 500
```

Chacune répond une `Response`, et chaque réglage répond de nouveau la réponse,
si bien qu'une ligne se lit d'un bloc :

```keal
html(page).status(201).type("text/html").with("x-made-by", "kealeb").cookie("sid", jeton, 3600)
```

Gardez une chaîne d'appels **sur une seule ligne**. Keal termine une
instruction au saut de ligne quand le jeton précédent pouvait en terminer une,
donc un `.` en début de ligne suivante est une nouvelle instruction, pas une
continuation.

`cookie(nom, valeur, maxAge, path, httpOnly, sameSite)` vaut par défaut
`HttpOnly`, `SameSite=Lax`, chemin `/`, et aucun `Max-Age` — ce qui veut dire
*cette session de navigateur*. `maxAge = 0` supprime.

`Content-Length` est toujours écrit d'après le nombre d'octets du corps et ne
peut pas être remplacé. Une longueur en désaccord avec son corps casse la
requête *suivante* plutôt que celle-ci : c'est un bug dont il vaut la peine de
refuser la possibilité.

## 5. Les pages

Une page est une fonction d'une requête vers un arbre de composants. Le
cadriciel l'enveloppe dans un document et l'envoie.

```keal
site.page("/a-propos", { req -> column([
    h1("À propos"),
    p("Deux paragraphes et un lien."),
    link("/", "accueil")
])}, "À propos de nous")
```

Le dernier argument est le `<title>` ; sans lui, c'est le titre de
l'application.

### L'arbre

Chaque constructeur répond un `Node`, et chaque réglage le répond de nouveau.

```keal
el("section").cls("hero").id("haut").attr("role", "banner").add(h1("Titre"))
```

| | |
|---|---|
| `el(balise)` · `elt(balise, enfants)` | n'importe quel élément |
| `txt(s)` | du texte — **toujours échappé** |
| `raw(s)` | du balisage déjà balisé, et qui doit être exactement un élément |
| `nothing()` | un nœud qui occupe une place et ne montre rien |
| `div` `span` `p` `h1` `h2` `h3` `strong` `em` `code` `pre` `br` `hr` | |
| `link(href, s)` · `img(src, alt)` | |
| `ul` `ol` `li` · `table` `thead` `tbody` `tr` `th` `td` `tdt` | |
| `section` `header` `footer` `nav` `main` | |
| `form` `label` `option` | |
| `.cls(noms)` `.id(v)` `.style(v)` `.title(v)` `.attr(n, v)` `.flag(n, oui)` | |
| `.add(enfant)` `.addAll(enfants)` `.on(événement, gestionnaire)` `.keyed(k)` | |

`.flag(nom, oui)` sert aux attributs booléens : il écrit `disabled` quand
`oui` et l'omet sinon, parce que `disabled="false"` désactive quand même.

### Les composants

`row`, `column` et `card` sont de la mise en page ; les autres prennent des
gestionnaires et ne signifient quelque chose que sur une page vivante.

```keal
row([button("Enregistrer", { e -> sauver() }), button("Annuler", { e -> retour() })])
column([field(nom, { e -> nom = e.value }), checkbox(actif, { e -> actif = e.checked() })])
select(choisi, [("a", "Alpha"), ("b", "Bêta")], { e -> choisi = e.value })
textarea(corps, { e -> corps = e.value })
shownWhen(n > 0, p("${n} en attente"))
```

`submit(texte)` est l'autre espèce : un bouton qui soumet son formulaire de
façon ordinaire, pour une page qui fonctionne sans aucun JavaScript.

### L'échappement

`txt` échappe. Il n'y a pas de drapeau pour l'en empêcher — `raw` est une
autre fonction, avec un autre nom, et c'est toute l'histoire de la sécurité
ici. Les valeurs d'attribut sont en plus échappées pour les guillemets.

### La feuille de style

Chaque page charge `/kealeb/kealeb.css` : une centaine de lignes, chaque règle
préfixée `kb-`, suivant le mode sombre du système. Pour mettre la vôtre :

```keal
site.style = "/static/app.css"     // la vôtre à la place
site.style = ""                    // aucune
site.head = "<link rel=\"icon\" href=\"/favicon.svg\">"
```

## 6. Les formulaires sans JavaScript

```keal
site.page("/saluer", { req -> column([
    h1("Saluer"),
    el("form").attr("method", "post").add(row([
        el("input").cls("kb-input").attr("name", "nom"),
        submit("Dire bonjour")
    ]))
])})

site.post("/saluer", { req ->
    val nom = req.form().get("nom") ?: ""
    html(doc("Saluer", h1("Bonjour, ${nom}")))
})
```

Rien ici n'a besoin de socket, de session ni de script. C'est toute la
troisième route de [`examples/hello.keal`](../examples/hello.keal).

## 7. Les pages vivantes

```keal
site.livePage("/", { req ->
    var compte = 0
    view({ -> column([
        h1("Cliqué ${compte} fois"),
        button("Cliquez-moi", { e -> compte = compte + 1 })
    ]) })
})
```

Deux fonctions, et la différence entre les deux est tout le modèle :

* **L'extérieure s'exécute une fois par visiteur.** Ce qu'elle capture est
  l'état de ce visiteur-là. Il n'y a pas de table de sessions à indexer
  correctement — la fermeture *est* la session.
* **L'intérieure s'exécute après chaque événement.** Elle doit être une
  fonction de l'état et de rien d'autre : ce qu'elle lit et qui peut changer
  sans événement ne sera pas remarqué avant le suivant.

### Ce qui se passe

1. Le navigateur demande la page. Le serveur construit l'arbre, numérote les
   nœuds qui écoutent, envoie le HTML, et garde l'arbre.
2. Un petit script ouvre un WebSocket vers `/kealeb/live`.
3. Vous cliquez. Le script envoie
   `{"i":"0.2.1","e":"click","v":"","f":{}}` — quel nœud, quel événement, ce
   qu'il contenait.
4. Le serveur exécute le gestionnaire, reconstruit l'arbre, le compare à celui
   qu'il avait gardé, et envoie la différence.
5. Le script l'applique. Six opérations existent et il n'y en a pas de
   septième : changer le texte d'un nœud texte, poser un attribut, retirer un
   attribut, remplacer un nœud, insérer un enfant, retirer un enfant.

Un gestionnaire est un `(Ev) -> Unit` :

| | |
|---|---|
| `e.name` | `click`, `input`, `change`, `submit`, `keydown` |
| `e.value` | ce que l'élément contenait — le texte du champ, `"true"`/`"false"` pour une case, l'option choisie |
| `e.number(défaut)` · `e.checked()` | la valeur, lue |
| `e.field(nom)` | un champ du formulaire sur `submit`, la touche sur `keydown` |

### La règle unique

**Un `Node`, un nœud dans le navigateur.** L'identité d'un nœud est sa
position — `0.2.1`, comptée depuis le point de montage — donc tout ce qui ne
rendrait aucun octet décalerait tout ce qui suit. C'est pour cela que
`nothing()` existe et rend un commentaire vide, et pour cela que `raw` doit
contenir exactement un élément.

C'est aussi pour cela qu'il n'y a pas encore de listes à clés : insérer en
tête d'une liste réécrit les libellés de tout ce qui suit. Correct, et plus de
travail qu'il n'en faut. `.keyed(k)` est accepté et réservé ; il ne fait rien
pour l'instant.

### Les sessions

Une session vit aussi longtemps que son socket, plus `ttlMs` (une minute par
défaut) pour l'onglet qui s'est endormi. Une page dont le serveur a oublié la
session se recharge elle-même et en obtient une nouvelle.

```keal
site.live.ttlMs = 300000        // cinq minutes
site.live.size()                // combien de pages sont ouvertes
site.live.refreshAll()          // reconstruire toutes les pages ouvertes
```

`refreshAll` est ce qu'on appelle quand le monde a changé sous toutes à la
fois — une ligne insérée par autre chose, une tâche terminée.

### Ce que cela coûte

Le serveur garde une session par page ouverte. Une page ouverte est de la
mémoire utilisée. C'est le marché de Vaadin et c'est celui que kealeb passe ;
si une page doit tenir cent mille onglets inactifs, ce doit être une `page` et
non une `livePage`.

## 8. Les fichiers statiques

```keal
site.files("/static", "./public")      // /static/a/b.css -> ./public/a/b.css
site.file("/favicon.svg", "./public/favicon.svg")
```

Chaque réponse porte un `ETag` fait de la date et de la taille du fichier, et
un client qui le renvoie obtient un 304 sans corps.

Tout chemin comportant un segment `..`, une barre initiale, une barre inverse
ou un composant caché est un **403** — refusé, pas normalisé. Normaliser un
chemin hostile, c'est ainsi qu'on sort d'un répertoire.

## 9. JSON

```keal
val champs: Map<String, Json> = {}
champs.set("id", jInt(7))
champs.set("nom", jStr("Ada"))
champs.set("etiquettes", jStrs(["a", "b"]))
jsonBody(jObj(champs).write())
```

À la lecture :

```keal
site.post("/commandes", { req ->
    val corps = parseJson(req.text())
    if (corps == null) { badRequest("ce n'est pas du JSON") } else {
        text("id ${corps.intAt("id")} pour ${corps.str("nom")}")
    }
})
```

`parseJson` répond un `Json?`. Du texte en trop est un refus, pas quelque
chose à ignorer. `field(nom)` répond un `Json?`, ce qui n'est pas la même
chose qu'un champ dont la valeur est `null` en JSON — et c'est pour cette
différence qu'il est nullable.

## 10. Les tests

Un gestionnaire est une fonction, donc l'essentiel d'un site se teste sans
aucun socket :

```keal
val r = Router()
r.get("/user/{id}", { req -> text("user ${req.param("id")}") })

assert(dispatch(r, request("GET", "/user/42")).text() == "user 42", "le paramètre")
assert(dispatch(r, request("GET", "/rien")).code == 404, "et rien d'autre")
```

`request(méthode, cible)` en construit une à la main. `dispatch(router, req)`
la passe dans la table.

Quand on veut vraiment le socket, on demande le port 0 et la machine en
choisit un :

```keal
val s = site.serverOn(0)
val port = s.open()          // le port réellement obtenu
s.tick(50)                   // un tour de boucle
```

`tools/test.sh` lance [`tests/units.keal`](../tests/units.keal) et, si `node`
est présent, [`tests/client.mjs`](../tests/client.mjs) — qui exécute le vrai
script client contre un vrai serveur.

## 11. La mise en service

```keal
site.run(8080)                        // 127.0.0.1 — ne peut surprendre personne
site.run(8080, "")                    // toutes les interfaces
site.log = false                      // pas de ligne par requête
```

Le serveur qu'elle construit se règle avant de démarrer :

```keal
val s = site.serverOn(8080)
s.maxHead = 16 * 1024                 // au-delà, c'est 431
s.maxBody = 2 * 1024 * 1024           // au-delà, c'est 413
s.idleMs = 15000                      // une connexion silencieuse est fermée
s.maxRequests = 500                   // par connexion, puis on ferme
s.handle = { req -> monPropreAiguillage(req) }
s.run()
```

Il n'y a pas de TLS. Mettez-le derrière un proxy inverse, qui est la place
d'un terminateur ; `X-Forwarded-For` arrive comme un en-tête ordinaire et
`req.peer` est le proxy.

La sortie standard est tamponnée par lignes dès le démarrage du serveur, donc
un journal redirigé vers un fichier ou un superviseur arrive au fil de
l'écriture.

## 12. Ce que le cadriciel ne fera pas

* Il ne compressera pas. Il ne parlera ni HTTP/2 ni TLS.
* Il ne lira pas un corps de requête en morceaux — il répond **501** et le
  dit.
* Il ne lira pas `multipart/form-data`, donc pas encore d'envoi de fichiers.
* Il n'exécutera pas votre gestionnaire sur un autre fil, donc un gestionnaire
  qui bloque bloque le serveur. Répondez, et revenez.
* Il n'échappera pas ce que vous mettez dans `raw`. C'est à cela que sert le
  nom.

---

## Où sont les choses

| fichier | ce qu'il contient |
|---|---|
| `runtime/kb.h` | toute la surface C : sockets, `poll`, blobs |
| `src/ffi.keal` | le seul fichier qui mentionne le C |
| `src/bytes.keal` | tampons d'octets, hexadécimal, Base64, SHA-1 |
| `src/text.keal` | encodage pour-cent, formulaires, cookies, dates HTTP |
| `src/http.keal` | `Request`, `Response`, le format du fil |
| `src/router.keal` | motifs, correspondance, aiguillage |
| `src/server.keal` | la boucle d'événements et l'automate par connexion |
| `src/ui.keal` | l'arbre de composants et le rendu |
| `src/theme.keal` | la feuille de style et le document |
| `src/json.keal` | JSON dans les deux sens |
| `src/ws.keal` | le tramage WebSocket |
| `src/live.keal` | les sessions, le diff, et le client du navigateur |
| `src/app.keal` | la porte d'entrée depuis laquelle tout ce qui précède est joignable |
