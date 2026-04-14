# REST API

This section documents the REST API endpoints available in the Magnate backend. All endpoints (except registration and login) require a valid JWT access token in the `Authorization` header.

## Authentication

### Register
::: magnate.views.RegisterView

### Login
::: magnate.views.LoginView

## User Information

### Profile
::: magnate.views.ProfileView

### User Played Games
::: magnate.views.GetGamesPlayedView

### User Name and Piece
::: magnate.views.UserNamePieceView

## Shop & Customization

### Shop Items
::: magnate.views.ShopItemListView

### Buy Item
::: magnate.views.BuyItemView

### User Owned Pieces
::: magnate.views.UserPiecesView

### User Owned Emojis
::: magnate.views.UserEmojisView

### Change Active Piece
::: magnate.views.ChangeUserPieceView

## Lobby & Matchmaking

### Get Private Code
::: magnate.views.GetPrivateCodeView

### Check Room Code
::: magnate.views.CheckPrivateRoomView

## Game Summary

### Game Summary
::: magnate.views.GetGameSummaryView
