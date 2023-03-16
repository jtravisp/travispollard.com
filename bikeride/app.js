// find quote div, set variable
let quotesDiv = document.getElementById('quotes')

// retrieve data from Kanye
fetch('https://api.kanye.rest')
.then(res => res.json())
.then(quote => {
    quotesDiv.innerHTML += `<p> ${quote.quote} </p>`
})
