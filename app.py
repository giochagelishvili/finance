from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd
import os
import sqlite3

os.environ["API_KEY"] = "pk_1a3770086ffa4ee69d0fb11fcff9feda"

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get the user id
    user_id = session['user_id']

    # Connect to database
    with sqlite3.connect('finance.db') as conn:
        # create a cursor object
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row

        # execute a SQL command for username and fetch results
        username = cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        username = username.fetchone()

        # extract username from results
        username = username[0]

        # execute a SQL command for stocks and fetch results
        user_portfolio = cursor.execute("SELECT * FROM stocks WHERE owner_id = ?", (user_id,))
        user_portfolio = user_portfolio.fetchall()

        # create list for storing stock symbols, names and amount of shares owned by the user
        symbols = []
        names = []
        shares = []

        # append user's stock's symbols, names and shares
        for i in user_portfolio:
            symbols.append(i['symbol'])
            names.append(i['stock_name'])
            shares.append(int(i['shares']))

        # create list for storing stock prices (real-time)
        stock_prices = []

        # append stock prices
        for i in range(len(user_portfolio)):
            # look up for stock in database and append real-time price
            stock = lookup(symbols[i])
            stock_prices.append(stock['price'])

        # create list for storing total value of stock (shares owned * current price)
        total_values = []

        # calculate and append total values
        for i in range(len(user_portfolio)):
            # look up the stock and extract stock price in float value
            stock = lookup(symbols[i])
            stock_price = float(stock['price'])

            # calculate and append total value
            total_values.append(shares[i] * stock_price)

        # execute a SQL command for cash and fetch results
        cash = cursor.execute("SELECT cash FROM users WHERE id = ?", (user_id,))
        cash = cash.fetchone()

        # extract cash from results
        cash = cash[0]

        # calculate value of total assets owned by user (cash + stocks)
        total_assets = float(cash) + sum(total_values)

        # close the cursor object
        cursor.close()

    # Display everything on the page
    return render_template("portfolio.html",
                           username=username,
                           cash=cash,
                           symbols=symbols,
                           names=names,
                           shares=shares,
                           stock_prices=stock_prices,
                           total_values=total_values,
                           total_assets=total_assets,
                           user_portfolio=user_portfolio)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Get symbol and shares input
        symbol = request.form.get('symbol').upper()
        shares = request.form.get('shares')

        # Return apology if any of input fields were left blank
        if symbol == "" or shares == "":
            return apology("Please enter symbol and amount of shares")

        # Look up the stock in database
        stock = lookup(symbol)

        # Return apology if symbol is not correct
        if stock == None:
            return apology("Incorrect symbol")

        # Return apology if number of shares is not positive integer
        if not shares.isnumeric() or isinstance(shares, float):
            return apology("Number of shares must be a positive integer")

        # Return apology if number of shares is less than or equal to zero
        if int(shares) <= 0:
            return apology("Number of shares must be a positive integer")

        # Get user id
        user_id = session['user_id']

        # Connect to database
        with sqlite3.connect('finance.db') as conn:
            # create a cursor object
            cursor = conn.cursor()
            cursor.row_factory = sqlite3.Row

            # run SQL command for user portfolio and fetch results
            user_portfolio = cursor.execute("SELECT * FROM stocks WHERE owner_id = ?", (user_id,))
            user_portfolio = user_portfolio.fetchall()

            # run SQL command for user's cash and fetch results
            cash = cursor.execute("SELECT cash FROM users WHERE id = ?", (user_id,))
            cash = cash.fetchone()

            # extract cash from result
            cash = cash[0]

            # return apology if user doesn't have enough cash to buy stocks
            total_cost = int(shares) * float(stock['price'])
            if total_cost > float(cash):
                # close the cursor object
                cursor.close()
                return apology("Insufficient funds")

            # if user doesn't own any stock
            if user_portfolio == []:
                # insert stock in user's portfolio
                cursor.execute("INSERT INTO stocks (owner_id, stock_name, shares, symbol) VALUES (?, ?, ?, ?);",
                               (user_id, stock['name'], shares, stock['symbol']))

                # update user's cash
                cash = float(cash) - total_cost
                cursor.execute("UPDATE users SET cash = ? WHERE id = ?;",
                               (cash, user_id))

                # update history
                cursor.execute(
                    "INSERT INTO history (owner_id, stock_symbol, stock_price, shares, transaction_type) VALUES (?, ?, ?, ?, 'BUY')",
                    (user_id, stock['symbol'], stock['price'], shares)
                )

                # close the cursor object and redirect to homepage
                cursor.close()
                return redirect("/")

            # if user already owns some stocks
            if user_portfolio != []:
                # run SQL command for stock symbols owned by user
                symbols = []
                for i in user_portfolio:
                    symbols.append(i['symbol'])

                # if user already owns the stock he's trying to buy
                if symbol in symbols:
                    # run SQL command for amount of shares owned by user and fetch the results
                    shares_db = cursor.execute(
                        "SELECT shares FROM stocks WHERE owner_id = ? AND symbol = ?;",
                        (user_id, symbol)
                    )
                    shares_db = shares_db.fetchone()

                    # extract shares from result
                    shares_db = int(shares_db[0])

                    # number of owned shares + number of shares user is trying to buy
                    shares_db += int(shares)

                    # update shares in database
                    cursor.execute("UPDATE stocks SET shares = ? WHERE owner_id = ? AND symbol = ?;",
                                   (shares_db, user_id, symbol)
                                   )

                    # update user's cash
                    cash = float(cash) - total_cost
                    cursor.execute("UPDATE users SET cash = ? WHERE id = ?",
                                   (cash, user_id)
                                   )

                    # update history
                    cursor.execute(
                        "INSERT INTO history (owner_id, stock_symbol, stock_price, shares, transaction_type) VALUES (?, ?, ?, ?, 'BUY')",
                        (user_id, stock['symbol'], stock['price'], shares)
                    )

                    # close the cursor object and redirect to homepage
                    cursor.close()
                    return redirect("/")

                # if user doesn't own the stock he's trying to buy
                elif not symbol in symbols:
                    # insert stock in user's portfolio
                    cursor.execute(
                        "INSERT INTO stocks (owner_id, stock_name, shares, symbol) VALUES (?, ?, ?, ?);",
                        (user_id, stock['name'], shares, stock['symbol'])
                    )

                    # update user's cash
                    cash = float(cash) - total_cost
                    cursor.execute(
                        "UPDATE users SET cash = ? WHERE id = ?;",
                        (cash, user_id)
                    )

                    # update history
                    cursor.execute(
                        "INSERT INTO history (owner_id, stock_symbol, stock_price, shares, transaction_type) VALUES (?, ?, ?, ?, 'BUY')",
                        (user_id, stock['symbol'], stock['price'], shares)
                    )

                    # close the cursor object and redirect to homepage
                    cursor.close()
                    return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    elif request.method == "GET":
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Get user id
    user_id = session['user_id']

    # Connect to database
    with sqlite3.connect('finance.db') as conn:
        # create cursor object
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row

        # run SQL command to fetch user's history
        history_db = cursor.execute(
            "SELECT * FROM history WHERE owner_id = ?",
            (user_id,)
        )
        history_db = history_db.fetchall()

        # create lists to store symbols, prices, shares, transactions and dates
        symbols_db = []
        prices_db = []
        shares_db = []
        transaction_type = []
        date = []

        # append data to lists
        for i in range(len(history_db)):
            symbols_db.append(history_db[i]['stock_symbol'])
            prices_db.append(float(history_db[i]['stock_price']))
            shares_db.append(history_db[i]['shares'])
            transaction_type.append(history_db[i]['transaction_type'])
            date.append(history_db[i]['date_added'])

    # display everything on page
    return render_template("history.html",
                           symbols_db=symbols_db,
                           prices_db=prices_db,
                           shares_db=shares_db,
                           transaction_type=transaction_type,
                           date=date,
                           history_db=history_db)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        with sqlite3.connect('finance.db') as conn:
            # create a cursor object
            cursor = conn.cursor()
            cursor.row_factory = sqlite3.Row

            # execute a SQL command and fetch results
            rows = cursor.execute("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
            rows = rows.fetchone()

            # close the cursor object
            cursor.close()

        # Ensure username exists and password is correct
        username_db = rows['username']
        username_input = request.form.get('username')

        hash_db = rows['hash']
        password_input = request.form.get('password')

        if username_db != username_input or not check_password_hash(hash_db, password_input):
            return apology("Invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        # symbol input from user
        symbol = request.form.get("symbol")

        # return apology if symbol was left blank
        if symbol == "":
            return apology("Please enter the symbol")

        # look up the stock in database
        stock = lookup(symbol)

        # return apology if stock could not be found
        if stock == None:
            return apology("Incorrect symbol")

        # if stock was found in database
        if stock != None:
            # stock symbol, name and price
            symbol = stock['symbol']
            name = stock['name']
            price = float(stock['price'])

            return render_template("quoted.html",
                                   symbol=symbol,
                                   name=name,
                                   price=price)

    elif request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Username provided by user on registration page
        username = request.form.get("username")

        # Password and password confirmation provided by user
        # on registration page
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Return apology if any field is left blank
        if username == "" or password == "" or confirmation == "":
            return apology("Please fill out every field")

        # Return apology if password and confirmation do not match
        if password != confirmation:
            return apology("Passwords do not match")

        # Register user into the database
        if password == confirmation:
            # Generate password hash
            hash = generate_password_hash(password)

            # Connect to database
            with sqlite3.connect('finance.db') as conn:
                # create a cursor object
                cursor = conn.cursor()
                cursor.row_factory = sqlite3.Row

                # run SQL command to fetch usernames from database
                users_db = cursor.execute(
                    "SELECT username FROM users;"
                )
                users_db = users_db.fetchall()

                # create list for storing usernames
                usernames_db = []

                # append fetched usernames in the list
                for i in range(len(users_db)):
                    usernames_db.append(users_db[i]['username'])

                # return apology if username already exists
                if username in usernames_db:
                    return apology("Username already exists")

                # execute SQL command to register user in database
                cursor.execute(
                    "INSERT INTO users (username, hash) VALUES (?, ?);",
                    (username, hash)
                )

                # commit changes do the database and close cursor
                conn.commit()
                cursor.close()

        # Log the user in
        return login()

    # User reached route via GET (as by clicking a link or via redirect)
    elif request.method == "GET":
        return render_template('register.html')


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Get user id
    user_id = session['user_id']

    # If request method is post
    if request.method == "POST":
        # Stock user wants to sell
        symbol = request.form.get("symbol")

        # Number of shares user wants to sell
        shares = request.form.get("shares")

        # Return apology if user didn't choose the stock
        if symbol == None:
            return apology("Please select stock you want to sell")

        # Return apology
        # if user didn't input number of shares
        # if number of shares is float
        # if number of shares is not a number
        if shares == "" or isinstance(shares, float) or not shares.isnumeric():
            return apology("Number of shares must be a positive integer")

        # Return apology if number of shares is less than or equal to zero
        if int(shares) <= 0:
            return apology("Number of shares must be a positive integer")

        # Connect to database
        with sqlite3.connect('finance.db') as conn:
            # get user id
            user_id = session['user_id']

            # create a cursor object
            cursor = conn.cursor()
            cursor.row_factory = sqlite3.Row

            # run SQL command to fetch symbols of stocks owned by the user
            symbols_db = cursor.execute(
                "SELECT symbol FROM stocks WHERE owner_id = ?;",
                (user_id,)
            )
            symbols_db = symbols_db.fetchall()

            # create list for storing symbols of stocks owned by the user
            symbols = []

            # append symbols in the list
            for i in range(len(symbols_db)):
                symbols.append(symbols_db[i]['symbol'])

            # return apology if user doesn't own the stock he's trying to sell
            if not symbol in symbols:
                cursor.close()
                return apology("You do not own this stock")

            # run SQL command to fetch number of shares of stock user owns
            shares_db = cursor.execute(
                "SELECT shares FROM stocks WHERE owner_id = ? AND symbol = ?;",
                (user_id, symbol)
            )
            shares_db = shares_db.fetchall()

            # extract number of shares from fetch result
            shares_db = shares_db[0]['shares']

            # return apology if user doesn't own enough shares
            if int(shares) > int(shares_db):
                cursor.close()
                return apology("You do not own enough shares to sell")

            # look up the stock in database
            stock = lookup(symbol)

            # get the stock price
            stock_price = stock['price']

            # run SQL command to fetch user's cash
            cash = cursor.execute(
                "SELECT cash FROM users WHERE id = ?;",
                (user_id,)
            )
            cash = cash.fetchall()

            # extract cash from fetch result
            cash = cash[0]['cash']

            # if user wants to sell every share they own
            if int(shares) == int(shares_db):
                # calculate total cost of stock they want to sell
                total_cost = float(stock_price) * int(shares)

                # calculate new amount of cash
                cash = float(cash) + total_cost

                # update user's cash
                cursor.execute(
                    "UPDATE users SET cash = ? WHERE id = ?",
                    (cash, user_id)
                )

                # update user's portfolio
                cursor.execute(
                    "DELETE FROM stocks WHERE owner_id = ? AND symbol = ?;",
                    (user_id, symbol)
                )

                # update history
                cursor.execute(
                    "INSERT INTO history (owner_id, stock_symbol, stock_price, shares, transaction_type) VALUES (?, ?, ?, ?, 'SELL');",
                    (user_id, stock['symbol'], stock['price'], shares)
                )

                # close cursor and redirect to homepage
                cursor.close()
                return redirect("/")

            # if user wants to sell some amount of shares they own
            if int(shares) > 0 and int(shares) < int(shares_db):
                # calculate total cost of shares they want to sell
                total_cost = float(stock['price']) * int(shares)

                # calculate new amount of cash
                cash = float(cash) + total_cost

                # calculate new amount of shares
                shares_db = int(shares_db) - int(shares)

                # update user's cash
                cursor.execute(
                    "UPDATE users SET cash = ? WHERE id = ?;",
                    (cash, user_id)
                )

                # update amount of shares owned
                cursor.execute(
                    "UPDATE stocks SET shares = ? WHERE owner_id = ? AND symbol = ?;",
                    (shares_db, user_id, symbol)
                )

                # update history
                cursor.execute(
                    "INSERT INTO history (owner_id, stock_symbol, stock_price, shares, transaction_type) VALUES (?, ?, ?, ?, 'SELL');",
                    (user_id, stock['symbol'], stock['price'], shares)
                )

                # close cursor and redirect to homepage
                cursor.close()
                return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    elif request.method == "GET":
        # Connect to database
        with sqlite3.connect('finance.db') as conn:
            # create cursor object
            cursor = conn.cursor()
            cursor.row_factory = sqlite3.Row

            # run SQL command to fetch symbols of stocks owned by the user
            symbols_db = cursor.execute(
                "SELECT symbol FROM stocks WHERE owner_id = ?;",
                (user_id,)
            )
            symbols_db = symbols_db.fetchall()

            # create list for storing symbols of stocks owned by the user
            symbols = []

            # append symbols to the list
            for i in range(len(symbols_db)):
                symbols.append(symbols_db[i]['symbol'])

            # close cursor and render sell.html
            cursor.close()
            return render_template("sell.html", symbols=symbols)
