import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, copy_current_request_context
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import error_response, login_required, lookup, format_money

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["format_money"] = format_money

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///user_profiles.db")


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/home")
@login_required
def index():
    
    profile = db.execute("SELECT symbol, SUM(shares) as shares, company_name FROM profile WHERE user_id = ? GROUP BY symbol", 
                         session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    total_cash = 0
    
    for asset in profile:
        asset["price"] = lookup(asset["symbol"])["price"]
        asset["value"] = asset["price"] * asset["shares"]
        total_cash += asset["value"]
    
    total_cash += cash
    
    return render_template("index.html", cash=cash, total_cash=total_cash, profile=profile)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        profile = lookup(symbol)
        
        if not symbol:
            flash("Must provide symbol")
            return redirect("/buy")
            
        elif profile == None:
            flash("Symbol does not exist")
            return redirect("/buy")
            
        
        if not shares:
            flash("Must provide shares")
            return redirect("/buy")
            
            
        try:
            shares = int(shares)
            if shares <= 0:
                flash("Must provide positive integer")
                return redirect("/buy")
                
        except ValueError:
            flash("Must provide a postive integer")
            return redirect("/buy")
            
        
        total_price = profile["price"] * shares
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        
        if cash >= total_price:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash - total_price, session["user_id"])
            db.execute("INSERT INTO profile (user_id, symbol, company_name, shares, price) VALUES (?, ?, ?, ?, ?)", 
                       session["user_id"], symbol, profile["name"], shares, profile["price"])
            
            time = db.execute("SELECT datetime('now','localtime')")
            db.execute("INSERT INTO history (user_id, symbol, shares, price, time, profit) VALUES (?, ?, ?, ?, ?, ?)", session["user_id"], 
                       symbol, shares, profile["price"], list(time[0].values())[0], 0)
            
            flash("Transaction Succesful - Shares Bought")
            return redirect("/home")
            
        else:
            flash("Cash is not enough")
            return redirect("/home")
            

    else:
        return render_template("buy.html")
    

@app.route("/history")
@login_required
def history():
    history = db.execute("SELECT * FROM  history where user_id = ?", session["user_id"])
    return render_template("history.html", history=history)


@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    
    if request.method == "POST":
        amount = int(request.form.get("amount"))
        
        user_cash = db.execute("SELECT cash from users WHERE id = ?", session["user_id"])[0]["cash"]
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user_cash + amount, session["user_id"])
        return redirect("/home")
    
    else:
        return render_template("add_cash.html")
        

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Must provide username")
            return redirect("/login")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Must provide password")
            return redirect("/login")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username and/or password")
            return redirect("/login")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/home")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/home")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        
        if not symbol:
            flash("Must provide symbol")
            return redirect("/quote")
        
        value = lookup(symbol)
        
        if value == None:
            flash("Must provide valid symbol")
            return redirect("/quote")
            
        else:    
            company_name = value["name"]
            company_price = value["price"]
            company_symbol = value["symbol"]
        
        return render_template("share_quote.html", company_name=company_name, company_price=company_price, company_symbol=company_symbol)
    
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    
    if request.method == "POST":
        
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Ensure username was submitted
        if not username:
            flash("Must provide username")
            return redirect("/register")
        
        # Ensure the username doesn't exists
        elif len(rows) != 0:
            flash("Username already exists")
            return redirect("/register")

        # Ensure password was submitted
        elif not password:
            flash("Must provide password")
            return redirect("/register")
            
        # Ensure password confirmation was submitted
        elif not confirmation:
            flash("Must confirm password")
            return redirect("/register")
        
        elif password != confirmation:
            flash("Passwords do not match")
            return redirect("/register")
            
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))
        return redirect("/home")
        
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        
        symbol = request.form.get("symbol")
        sell_shares = request.form.get("shares")
        
        if not symbol:
            flash("Stock not selected")
            return redirect("/sell")

        if not sell_shares:
            flash("Must provide a valid number of shares")
            return redirect("/sell")
        
        sell_shares = int(sell_shares)
        
        if sell_shares < 1:
            flash("Must be a valid number")
            return redirect("/sell")
        
        user_shares = db.execute("SELECT SUM(shares) as shares FROM profile WHERE user_id = ? AND symbol = ?", 
                                 session["user_id"], symbol)[0]["shares"]
    
        if not user_shares:
            flash("Please provide a stock you own")
            return redirect("/sell")
        
        if sell_shares > user_shares:
            flash("You do not own this number of shares of this stock")
            return redirect("/home")
        
        price = lookup(symbol)["price"]
        total_stock_price = price * sell_shares
        company_name = lookup(symbol)["name"]
        
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash + total_stock_price, session["user_id"])
        
        remaining_shares = user_shares - sell_shares
        buy_price = db.execute("SELECT price FROM history WHERE user_id = ? AND symbol = ? AND shares >= ? ORDER BY time DESC LIMIT 1", session["user_id"], symbol, sell_shares)[0]["price"]
        time = db.execute("SELECT datetime('now','localtime')")
        
        if remaining_shares <= 0:
            db.execute("DELETE FROM profile WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
            
            db.execute("INSERT INTO history (user_id, symbol, shares, price, time, profit) VALUES (?, ?, ?, ?, ?, ?)",
                       session["user_id"], symbol, -sell_shares, price, list(time[0].values())[0], (price-buy_price) * sell_shares)
                       
            flash("Transaction Succesful - Shares Sold")    
            return redirect("/home")
        
        else:
            db.execute("DELETE FROM profile WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
            db.execute("INSERT INTO profile (user_id, symbol, company_name, shares, price) VALUES (?, ?, ?, ?, ?)",
                       session["user_id"], symbol, company_name, remaining_shares, price)
            
            
            db.execute("INSERT INTO history (user_id, symbol, shares, price, time, profit) VALUES (?, ?, ?, ?, ?, ?)",
                       session["user_id"], symbol, -sell_shares, price, list(time[0].values())[0], (price-buy_price) * sell_shares)
            
            flash("Transaction Succesful - Shares Sold")    
            return redirect("/home")
        
    
    else:
        symbols = db.execute("SELECT symbol FROM profile GROUP BY symbol")
        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return error_response(e.name, e.code)

# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
